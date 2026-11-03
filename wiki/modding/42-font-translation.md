---
id: "modding-font-translation"
title: "Import and validate a translation font"
description: "A full workflow for choosing the correct game font, importing TTF/OTF/TTC glyphs, character scope, offsets, spacing, smoothing, CP932 limits, memory cost, and UI testing"
games: ["path-of-radiance"]
section: "modding"
article_type: "tutorial"
tags: ["Guide", "Modding app", "Fonts", "Translation", "Localization"]
aliases: []
status: "draft"
last_reviewed: "2026-10-17"
sources: ["telliusmodding-source", "tellius-archive-research"]
cms_collection: "modding"
source_path: "modding/42-font-translation.md"
tutorial_kind: "task"
tutorial_track: "dialogue-and-text"
tutorial_stage: "draft"
prerequisites: ["modding-inline-text-and-fonts", "modding-base-and-world-map-text"]
verification: ["source-reviewed", "unknown"]
---
# Import and validate a translation font

**Route:** Assets → Fonts → Import TrueType/OpenType font...

## What you will make

You will replace a controlled subset of the Path of Radiance **talk** font with glyphs from a licensed TTF/OTF/TTC, keeping Japanese glyphs the source lacks. You will tune size, horizontal/vertical offset, advance spacing, and smoothing against a before/after preview, save the font, and test the same character corpus in dialogue, text log, menus, numbers, and long labels.

You will also determine which requested translation characters cannot exist in the game's CP932/Shift-JIS text encoding. Importing a glyph image is useful only when message/menu bytes can name that character.

## Before you begin

Complete [Control dialogue text, timing, icons, and fonts](39-inline-text-and-fonts.md). Choose a font whose license permits embedding/redistribution in the mod. Record its license and version alongside the project.

Create a corpus containing:

- uppercase/lowercase Latin letters;
- digits and punctuation;
- narrow/wide pairs such as `IlMW` and `1/8`;
- parentheses, apostrophes, quotes, dash/ellipsis forms actually used;
- every accented/special character requested by the translation;
- longest dialogue line, menu label, item/class name, objective line, and staff name;
- representative kana/kanji that must remain intact.

Before importing, open **Assets → Fonts**, select **talk**, paste the corpus into **Preview text**, and record missing/fallback characters, line height, clipping, and width. Use **Export sheets as PNG...** to preserve a visual baseline, and keep the original file through the project's backup system.

Do not start by replacing all five fonts. Prove the talk font, then repeat a separate matrix for system/menu use.

## How the editor fits together

Path of Radiance uses five bitmap fonts with different consumers:

| Font | File/use | Translation risk |
| --- | --- | --- |
| **system** | compressed `.cms`; menus, status, shops, tutorials, nameplates | broad UI fit and numeric alignment |
| **fe_font** | Tellius alphabet (`#F01`) | replacing changes ancient-language appearance |
| **talk** | dialogue/text log (`#F02`) | line width, portraits/boxes, backlog |
| **bigkana** | title/file menu (`#F03`) | large labels and limited glyph set |
| **alpha** | staff roll (`#F04`) | credit widths/order/presentation |

The viewer shows each font's state, path, glyph count, sheet count/size, ascent, descent, and uncompressed size. **Preview text** renders with current game metrics. **Sheet** displays the raw grayscale bitmap pages.

An import rasterizes the chosen outline font into the selected game's bitmap-font structure. It preserves the base font's ascent, descent, and sheet size so existing line positions stay stable. It can replace all existing characters or only an explicit subset, and can add CP932 characters not already present.

For Path of Radiance, fonts 1–4 also exist inside `system.cmp`; the project build refreshes those bundled copies from the edited loose files. The system font is stored as compressed `system.cms`. Building—not just editing—is required to deliver the copies the game actually loads.

## Guided walkthrough

### 1. Select the correct consumer font

Open **Assets → Fonts** and select **talk**. Read **Used for**, file path, glyph/sheet counts, ascent/descent, and uncompressed KB. Enter the test corpus in **Preview text** and browse each sheet.

Confirm the content you intend to change actually uses talk. Menus normally use system; title/file labels can use bigkana; staff roll uses alpha; ancient lines explicitly switch to fe_font. Importing into the wrong file can produce a perfect preview that never affects the target screen.

### 2. Open the import dialog and choose the source

Choose **Import TrueType/OpenType font...**, then **Browse...** for the TTF, OTF, or TTC. The dialog shows the game font above and candidate import below. It updates after setting changes.

Start with:

- **Size** = Auto;
- **Move right** = 0;
- **Move down** = 0;
- **Extra spacing** = 0;
- **Smooth edges** enabled;
- **Only these** with a small safe ASCII test subset.

Auto chooses a pixel size whose capital H approximates the existing game's H/baseline target, falling back to ascent where needed. It is a starting point, not proof that lowercase, punctuation, or accents fit.

### 3. Limit the first import scope

Choose **Only these** and paste a unique controlled set such as:

```text
ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?'-()
```

This replaces only those reachable characters and leaves every other existing game glyph intact. Use **Also add** only for characters absent from the game font that have a valid CP932 code.

The alternative, **Every character talk has**, attempts to replace the full existing glyph inventory; if the source outline font lacks one, the original game bitmap is kept. This is useful later for a broad conversion but can mix visual styles unexpectedly.

Read the summary after every update:

- **replaced**: existing game glyphs rasterized from the source;
- **added**: new encodable glyph records created;
- **kept**: source lacks them, so original game glyphs remain;
- **No game encoding, skipped**: Unicode characters cannot be represented in CP932 and no message byte can reach them;
- file-size delta: additional memory/load cost.

### 4. Tune size before offsets

Compare cap height, x-height, punctuation, and digits. Change **Size (px)** by one step at a time. Use the smallest size that remains readable while fitting the target line height.

The game font's ascent/descent do not expand to accommodate taller imports. A glyph that looks good in an isolated preview may clip above/below in a real textbox. Include tall ascenders, descenders (`gjpqy`), accents, and punctuation in the preview.

### 5. Tune vertical and horizontal bearings

Use **Move down** to align the visual baseline. Positive values move glyphs down; negative move them up. Compare capital letters, lowercase baseline, punctuation, and descenders together.

Use **Move right** only when the whole family sits incorrectly within its boxes. It changes glyph horizontal bearing, not the advance between glyph origins. A right shift can create apparent leading padding or right-edge clipping.

Keep each change within the dialog's -20 to +20 ranges and record the chosen values.

### 6. Tune advance with Extra spacing

**Extra spacing** adds to every imported glyph's advance. It does not make the bitmap wider. Test tightly packed pairs (`rn`, `ll`, `AV`) and long lines.

Negative spacing can make glyphs collide; positive spacing can overflow menus/boxes. The allowed dialog range is -10 through +20, but a translation font normally needs small changes. Check digits in columns because existing UI may expect stable numeric width.

### 7. Compare smoothing

Toggle **Smooth edges**. Enabled creates grayscale coverage appropriate to the game's I4 sheets; disabled produces hard-edged masks. Inspect at actual game scale, not only zoomed sheets.

Smoothing can improve curves but make thin strokes appear lighter against bright backgrounds. Choose based on dialogue and menu captures in the target renderer.

### 8. Stage and save the font

When the candidate summary and preview are acceptable, choose **Import**. This stages the converted font in memory; the main font list marks it **Unsaved** and reports replaced/added counts, source filename, and pixel size.

Test additional strings in the main **Preview text** and inspect every generated **Sheet**. If wrong, choose **Discard changes** and repeat. When ready, choose **Save**. `.cms` is recompressed automatically; GCF fonts are written in their native form.

Switch away and back. The state should be **Modified**, not Unsaved, and metrics/glyph count should persist.

### 9. Test dialogue and text log

Put the corpus into a disposable dialogue message using ordinary talk font. Test every page at actual message speeds, open the Z text log, and inspect:

- baseline and clipping;
- wrap/box overflow;
- punctuation and apostrophes;
- fallback star/space;
- portrait/nameplate alignment;
- log rendering.

If the source lacks kana/kanji, verify that **kept** glyphs still render. A mixed source/original style is expected unless you provide replacements.

### 10. Repeat deliberately for system/UI font

Only after talk passes, select **system** and start a separate import with its own settings. Test status screen, forecast, inventory, shops, options, tutorials, objectives, nameplates, save/file UI, numbers, and long localized labels.

Do not copy talk size/offset/spacing blindly. System font metrics and layout consumers differ. Numeric columns and tiny labels can fail even when dialogue looks good.

### 11. Build and verify loaded copies

Build the project so fonts 1–4 are synchronized into `system.cmp`. Launch Dolphin from a fresh boot; font files are boot-loaded, so hot state may retain old glyphs.

Run the complete corpus matrix in-game. Record file-size/memory changes and test a long session crossing menus, dialogue, base, battle forecast, and credits where applicable.

## Understand every control

### Font list and state

- **Font** chooses the bitmap file/consumer.
- **State** is Vanilla, Unsaved, or Modified.
- **Used for** summarizes the primary consumer; inline `#F` can override in messages.
- Info shows path, glyphs, sheets, sheet size, ascent, descent, and uncompressed KB.

### Preview text and sheets

**Preview text** renders through the selected game font and its current pending data. It catches missing encoding/glyph issues and approximate widths. **Sheet** browses bitmap atlases; it is useful for clipping/packing artifacts but does not show layout context.

### Import scope

- **Every character ... has** targets all existing base glyphs; source-missing ones are kept.
- **Only these** restricts replacement to the literal character set entered.
- **Also add** requests new encodable characters not already in the base font.

Repeated characters are effectively one glyph request. Encoding, not Unicode range or source-font coverage, is the hard reachability boundary.

### Raster controls

- **Size (px)** selects outline raster size; Auto matches capital H to existing metrics.
- **Move right** changes horizontal bearing (-20 to 20).
- **Move down** changes vertical placement (-20 to 20).
- **Extra spacing** adds to advance (-10 to 20).
- **Smooth edges** toggles antialiased grayscale masks.

### File actions

- **Import** stages candidate data; it does not write immediately.
- **Save** writes all pending fonts.
- **Discard changes** clears all pending imports in the panel.
- **Restore original file** puts the disc's version of the selected font back.
- **Export sheets as PNG...** exports visual sheets for audit/reference; PNGs are not importable font definitions by themselves.

## Interactions and precedence

- Message `#F` selection determines which imported font renders a line.
- Character encoding happens before glyph lookup; unencodable Unicode cannot be fixed by adding a bitmap.
- If a code is encodable but missing, fallback is white star where available, otherwise the first/space glyph.
- Import preserves ascent/descent and sheet dimensions, so size/offset must fit the existing line contract.
- Spacing changes advance, while Move right changes bearing; they solve different alignment problems.
- Source-missing glyphs are kept, potentially mixing styles.
- Added glyphs/file growth increase boot-loaded memory use.
- Fonts 1–4 must be refreshed inside `system.cmp` during build; loose-file inspection alone is insufficient.
- Title-card art and battle-scene digit textures are not controlled by these fonts.
- Each font consumer needs its own fit matrix; talk success does not prove system-menu success.

## Test matrix

| Area | Corpus/state | Pass condition |
| --- | --- | --- |
| Import summary | safe subset | expected replaced/added/kept/unencodable counts |
| Capitals/lowercase | `HgjpqyIlMW` | no clipping, stable baseline, readable weight |
| Digits | `0123456789 42/42` | widths/columns remain usable |
| Punctuation | quotes, apostrophe, dash, ellipsis, brackets | correct glyphs and spacing |
| Dialogue | longest translated line | fits intended box or wraps intentionally |
| Text log | same dialogue | no fallback/clipping and readable speaker context |
| Menu/system | longest labels/numbers | no overlap/truncation introduced by font metrics |
| Preserved Japanese | kana/kanji samples | source-missing game glyphs retained |
| Unsupported Unicode | requested unencodable set | explicitly reported/skipped; translation plan adjusted |
| Fresh boot build | Dolphin after rebuild | bundled fonts reflect saved import |

## Troubleshooting

### A requested accented letter is reported unencodable

It has no CP932 code and cannot be named by normal game text. Choose an encodable substitute, redesign the translation, or undertake a separate encoding/code patch. A larger Unicode font file alone cannot solve it.

### Glyphs clip at top or bottom

Reduce Size or adjust Move down. Ascent/descent remain the game's values. Test ascenders and descenders together before saving.

### Text is offset but spacing changes make it worse

Use Move right/down for bitmap placement; use Extra spacing only for pen advance. Restore spacing to zero and tune bearing first.

### Japanese glyphs look unchanged beside new Latin

The source lacked them and the importer kept original bitmaps. This is safe but stylistically mixed. Supply a source containing them only if licensing and coverage are appropriate.

### Preview changed but Dolphin still shows vanilla glyphs

Save, rebuild so `system.cmp` is synchronized, and cold-boot the game. Confirm you edited the actual consumer font and not only a similar one.

### Menus overflow after a successful dialogue test

Talk and system are different fonts/consumers. Restore/tune system separately and test its longest/narrowest UI contexts.

### File size grows sharply

Reduce added/replaced scope, pixel size, or unnecessary glyph coverage. Review sheet/glyph count and memory implications; do not import an entire outline-font Unicode repertoire.

## Save, build, and revert

Choose **Save**, reopen the font, and inspect state/metrics. Build to refresh compressed/bundled copies, then cold-boot Dolphin.

To revert pending work, use **Discard changes**. To revert a saved font, use **Restore original file**, then rebuild so `system.cmp` copies match. If several fonts were saved together, restore each affected file and verify the archive rebuild.

Keep the licensed source font and chosen settings in project documentation, but distribute it only as permitted by its license.

## Limits and confidence

The five-font ownership, viewer/import controls, ranges, CP932 boundary, fallback behavior, preserved metrics, file synchronization, and import result categories are source-reviewed. Visual quality and memory/performance thresholds are design/runtime matters and depend on the chosen source and coverage.

Preview is a faithful bitmap renderer but not every UI layout. Final clipping, widths, smoothing, boot loading, and long-session stability require Dolphin testing across real consumers.

## Things to try

- Import only `A`, compare Auto size with ±1 px, and inspect sheet/line placement.
- Add one encodable character absent from talk and prove it changes from fallback to real glyph.
- Enter one unencodable character to document the exact summary behavior.
- Compare Smooth edges on/off at native scale and on a bright background.
- Use identical source/settings for talk and system, then document why their outputs/fit still differ.
- Export before/after sheets and create a glyph-coverage review image for translators.

## Related tutorials and references

- [Control dialogue text, timing, icons, and fonts](39-inline-text-and-fonts.md)
- [Edit support, base, and world-map conversations](40-base-and-world-map-text.md)
- [Font format](../formats/font-format.md)
- [Message format](../formats/message-format.md)
- [Dialogue engine](../systems/dialogue-engine.md)

---

[← Previous: Set chapter title cards and full-screen movies](41-chapter-opening-movies.md) · [All tutorials](index.md) · [Next: Read and edit AI scripts →](43-ai-language.md)
