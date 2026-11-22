# Tellius Modding v1.0.0.0

The first stable release. Path of Radiance and Radiant Dawn are now edited from the
same pages, Radiant Dawn works on the US, European and Japanese discs, and all but
a few kilobytes of both games are read by a decoder the app uses.

## Highlights

- **Radiant Dawn on every region.** The US (RFEE01), European (RFEP01) and Japanese
  (RFEJ01) discs open, build and play. Game Code patches, the chapter jump and hub
  routing are ported to each disc's `main.dol` and checked against it; text uses each
  disc's own encoding, including the European letters.
- **One page per task for both games.** Saves, Battle Data and Battle Cameras are now
  single pages that adapt to the game, with the same tabs and controls for Path of
  Radiance and Radiant Dawn.
- **Radiant Dawn saves.** Units (class, items, skills, supports, copy to a new slot,
  remove), map objects, flags named from the scripts and the system record (clears,
  unlocks, characters met, conversations seen, Sound Room, glossary, clear records).
  US, European and Japanese files open; edited files load in the game.
- **New Radiant Dawn editors.** Glossary and relation chart, Conversation Room,
  endings, class introductions, movie subtitles, world-map route lines and the Wii
  channel banner. Each file rebuilds byte for byte on all three discs.
- **Decoding coverage.** On the US discs, the bytes left undecoded or unclassified are
  about 0.003 % of Path of Radiance and 0.0006 % of Radiant Dawn (down from 1.51 %), with
  the same figure on the European and Japanese Radiant Dawn discs.
- **The Tellius Archive covers both games.** Lessons and systems pages gain
  "On Radiant Dawn" sections.
- **Open source under the MIT License.** The code can be used, changed and shared
  freely; see the License section below.

## Radiant Dawn

### Discs and regions

- European and Japanese discs: Game Code entries, story order, hub routing and chapter
  jump get their own sites, moved from the US ones through a stored address table and
  checked against each retail `main.dol`. The Japanese disc leaves out the Wrath HP
  threshold, whose rule differs there.
- European text: the single-byte table of the European fonts (`fe10_eu`) is used by
  the Dialogue editor and text export.
- Japanese data: item and skill records without an article, chapter message labels,
  title cards, the conversation preview's language and wide assets, and the music
  archive follow the disc's own files.
- Movies with several audio tracks (the European scene movies, one per language) are
  read, and a replacement keeps the track count.
- The staff roll is shown in the file's own encoding, with each disc's languages,
  line counts, title and copyright.

### Saves

- Radiant Dawn's `FE10_US.dat`, `FE10_EU.dat` and the Japanese file open on the shared
  Saves page. Record magics carry the region letter; the Japanese file is the US layout
  cut after the first checkpoint.
- Units: class, army, items, skills and supports, with **Copy to new slot** and
  **Remove** (refused while another unit links to it).
- Map objects: the map's tile records, as on Path of Radiance.
- Flags: campaign and chapter flags named from `startup.cmb` and the chapter script.
- System data: every part of the system record is named from its reader; bits are
  numbered as the game numbers them.
- Play from a save in Dolphin accepts every known size.

### Game Code

- Class critical bonus multiplier (retail Radiant Dawn never gives `SID_CRITRISE`, so
  the row matters once your data does).
- Story-promoted units can use promotion items (`SID_EVENT_CC` is a class skill of
  Hero, Rogue, Light Mage and Light Sage).
- Animate ally and NPC battles.
- Animation speed.
- Free camera rotation now also lifts the analog-stick camera's limits and ease-back.
- Chapter jump: empties the unit lists, runs the chapter-state init like the file
  menu, skips the opening movie, and boots the European and Japanese discs.

### Maps, hubs and models

- Map settings: map wrapping (on/off, X/Y step, transition) and the height ceiling.
- Map objects: **Mirror model in X** and 1/64-tile X/Y offsets, drawn by the Build
  canvas, the 3D view and the height tools.
- Create hub can make a blank map on Radiant Dawn, renamed like an added chapter's
  copy so the game finds its ground and terrain.
- New skeletons can be fitted on Radiant Dawn map units: the pose model now applies
  the loader's joint-orient rule.
- Window images preview Radiant Dawn layouts and backgrounds.

### Game data and checks

- **Remove** on Game Data and the Stats form refuses a character, class or item that a
  game file still names (scripts, deployments, shop, battle and animation tables,
  `main.dol`), as on Path of Radiance.
- **Export as text** adds faces and the 21 `FE10Battle` tables.
- Battle Data edits `FE10Battle.cms` (names and scenery choices); Battle Cameras edits
  clips against the registry, with rig preview and clip import.

### Checked in the game

Each of these was run in Dolphin and compared with retail: placement mirror and
offsets, the water flag, a rig round trip, staff roll edits, map wrap, a blank hub,
edited European and Japanese saves, promotion items on story units, map light and fog,
class introductions, animation speed, animated ally and NPC battles, glossary edits,
Extras unlocks, Conversation Room order and subtitle edits.

## Path of Radiance

- **Roster tab** on chapter pages: pick a fixed team or the player's army, set the
  team's tiles, set every other unit aside, and choose who joins or leaves the army at
  the end of the chapter, without writing script. **Check turn 1** shows who is on the
  map with a new save and with a full army. The playthrough simulator now follows the
  game's army rule for `_mikata_` groups.

## Both games

- Saves, Battle Data and Battle Cameras are one page each (`battle_browser`), with a
  per-game adapter. The four per-game viewers are gone.
- Build tab map image: tile (0,0) is drawn top-left, matching the grid.
- Object flag edits keep the bits no control shows.
- Paragon-style discs (IDs such as GFEE02), latin-1 file names, `system.cmp` data and
  `.cmb` padding are handled.

## Decoding coverage

The coverage tool walks every file on the disc and reports each byte as decoded,
plausible or open. Movies and `.stm` music are left out, and on Radiant Dawn the Wii
HOME Menu's sound banks and `client.bin`. Radiant Dawn's sound archives (`.brsar`,
48 MB each) are placed byte by byte, with nothing left open on any disc:

| Disc | Undecoded or unclassified |
|---|---|
| Path of Radiance US (GFEE01) | 20.6 KB (about 0.003 %), of which 18.3 KB is `client.bin`; 2.3 KB without it |
| Radiant Dawn US (RFEE01) | 12.4 KB of 2.07 GB (0.0006 %) |
| Radiant Dawn Europe (RFEP01) | 15.2 KB of 2.54 GB (0.0006 %) |
| Radiant Dawn Japan (RFEJ01) | 11.8 KB of 1.85 GB (0.0006 %) |

New on Radiant Dawn: every `.ga` animation footer slot (bone visibility, events and
their sound-effect codes, material alpha and colour, texture motion, particle
emitters), all of `FE10Battle`, `sound_data` (every cue parameter and `SND_*` table),
`.gs` material, texture and bone flags, field rules for `FE10Anim`,
`FE10Conversation`, `FE10Growth`, `FE10Effect`, `map.bin`, rect layouts and the staff
roll, every font, the Wii banner, and the Wii HOME Menu's archives, layouts, textures
and songs.

Still open on RFEE01, by size: `FE10Effect` flags and parameters (5 KB), `FE10Anim`
flags and data parameters (2.9 KB), a curve field in 14 `.ga` files (2.4 KB),
`FE10PersonGrowth` (1 KB) and a few hundred bytes of conversation, map and table
fields. The European and Japanese discs leave the same fields open. Path of Radiance
was measured on the US disc.

## Tellius Archive

- "On Radiant Dawn" sections in the modding lessons (Game Data, maps and deployments,
  scripts and text, AI and models, tools) and in the systems pages (combat, skills,
  classes, growth, laguz, weather, maps, events, items, economy, bases, preparations,
  status effects, objectives, supports, saves, campaign flow, AI, battle staging).
- Format pages for the new Radiant Dawn table files, route lines and the Wii banner.

## For contributors

- `tools/affected_tests.py` runs only the tests that import changed code.
- `tools/release_check.py` runs every check that needs the game data in one command
  (both games' disc tests, every region, the coverage of each disc and every `.ga`
  round trip) and ends with one pass/fail table.
- Disc tests check a fixed sample by default (`TELLIUS_CORPUS=full` walks everything)
  and run in parallel with pytest-xdist; every Radiant Dawn disc test runs on the US,
  European or Japanese disc.
- `tools/dolphin_input.py` drives a running Dolphin (keys, screenshots, save states)
  for in-game checks; `build --set rdcheck` builds the controller-driven check set.

## Known limitations

- Left open for this release: the Wii HOME Menu's sound banks and `client.bin` (the GBA
  program). Their bytes are kept as they are.
- A chapter jump into Radiant Dawn's Endgame can't reach the endings: the game reads the
  top unit of an empty army after the slideshow.
- Disc-backed tests need your own extracted games and do not run in CI.
- See [known bugs](https://github.com/klg-tellius/TelliusModding/blob/main/docs/app/known-bugs.md)
  for the remaining confirmed defects.

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
FFmpeg directly from their upstream sites. Downloads are checksum-verified.
Internet access is needed for this setup step. Game data is not included.

To share a mod, make a `.tpatch` on the Disc & Patch page and give it out with
**TelliusPatcher.exe**, which applies it to the player's own disc.

Keep the `_internal` folder next to the executable. The build is unsigned.
The accompanying `.sha256` files provide the checksums.

Documentation: https://klg-tellius.github.io/TelliusModding/
