# Tellius Modding v1.0.0.1

A fix release for **Tellius Patcher**, the program players run to apply a mod's
`.tpatch`. Mod authors should hand out this TelliusPatcher.exe instead of the 1.0.0.0
one.

## Fixes

- **WIT download no longer fails on a slow or blocked connection.** The patcher tried
  wit.wiimm.de once and stopped with `urlopen error [WinError 10060]` when the site did
  not answer. It now retries, then downloads the identical file from this project's
  `tools-mirror` release; the pinned SHA-256 is checked whatever the source.
- **A WIT you already have can be used.** If no download works, the patcher explains
  what to download and lets you choose `wit.exe` or the WIT `.zip` (checksum-checked).
  WIT placed next to TelliusPatcher.exe, or on the `PATH`, is used without any download,
  so a mod author can ship it with the patch.
- **`.rvz` discs work without the full app.** DolphinTool, which reads `.rvz` images,
  was only looked for next to the Dolphin set in the app's settings. The patcher now
  also looks in the usual Dolphin folders, next to itself and on the `PATH`, and
  otherwise asks for the Dolphin folder once and remembers it.

Everything else is unchanged from
[v1.0.0.0](https://github.com/klg-tellius/TelliusModding/releases/tag/v1.0.0.0).

## License

From this release, the Tellius Modding code is released under the
[MIT License](https://github.com/klg-tellius/TelliusModding/blob/main/LICENSE); the
ZIP carries it as `licenses/TelliusModding-LICENSE.txt`. The Tellius Archive's
original text and diagrams stay under CC BY-SA 4.0 (`CONTENT-LICENSE.md`), and
third-party components keep their own terms.

Neither license covers Nintendo or Intelligent Systems game data, trademarks or other
game-derived material. No game data is included: you need your own disc, and a
`.tpatch` holds only your changes.

## Install

Download **TelliusModding-Windows-x64.zip**, extract it completely, and open
**TelliusModding.exe**. Python and the app's Python dependencies are included; no
pip commands or administrator access are needed.

On first launch, choose **Download missing tools** to install WIT and optional
FFmpeg from their upstream sites (WIT falls back to this project's copy when
wit.wiimm.de does not answer). Downloads are checksum-verified.
Internet access is needed for this setup step. Game data is not included.

To share a mod, make a `.tpatch` on the Disc & Patch page and give it out with
**TelliusPatcher.exe**, which applies it to the player's own disc.

Keep the `_internal` folder next to the executable. The build is unsigned.
The accompanying `.sha256` files provide the checksums.

Documentation: https://klg-tellius.github.io/TelliusModding/
