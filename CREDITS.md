# Credits and research resources

Tellius Modding brings together format research, a Python editor, and documentation
for Fire Emblem: Path of Radiance and Radiant Dawn.

## Research resources

- [Zheneq's Noesis plugins](https://github.com/Zheneq/Noesis-Plugins), especially
  `fmt_fireemblem_gs.py`: a reference for investigating the `.g` skeleton and `.gs`
  mesh formats. The project maintainer identifies this as a resource used during
  reverse engineering, not a source-code port. The plugin is not bundled here.
- [Ghidra](https://github.com/NationalSecurityAgency/ghidra): executable analysis
  and documentation of game behavior and data structures.
- [Dolphin](https://github.com/dolphin-emu/dolphin): game execution and debugging
  used to check format and rendering behavior.
- [FE9 Character Editor and Randomizer](https://github.com/jespoketheepic/FE9-Character-Editor-and-Randomizer):
  reference cited by the event-script reader.
- [vgmstream](https://github.com/vgmstream/vgmstream): audio-decoding behavior
  used as a cross-check for DSP-ADPCM.

- Ralf's public `GFEP01` Gecko/AR code thread on
  [GC-Forever](https://www.gc-forever.com/forums/viewtopic.php?t=2203) (debug menus,
  development mode, ally/NPC battle animations, growth modes, fog of war, free camera,
  reinforcement uses, critical-hit options): used as reverse-engineering leads,
  re-derived and verified against the US, PAL and JP executables.

These acknowledgments identify useful resources; they do not imply endorsement
or assign their authors ownership of this project's code.

## Incorporated third-party implementation

`App/fe_modding/formats/dsp_adpcm.py` credits an adaptation of Alex Barney's
[DspTool](https://github.com/Thealexbarney/DspTool) DSP-ADPCM implementation.
The [full MIT copyright and permission notice](App/licenses/DspTool-MIT.txt)
is included and must remain with that implementation.

## Dependencies and external tools

Python dependencies are listed in [App/requirements.txt](App/requirements.txt):
Pillow, NumPy, fontTools, Sun Valley ttk (`sv-ttk`), and wgpu-py. Portable releases
include these dependencies and their notices. Source installations use pip.
All dependencies retain their respective licenses.

- [Wiimm's ISO Tools](https://wit.wiimm.de/): disc extraction and build operations.
  See [origin information](App/tools/wit/ORIGIN.txt) and
  [GPL v2 notice](App/tools/wit/gpl-2.0.txt).
- [FFmpeg](https://ffmpeg.org/): general audio/video decoding.
  See [origin information](App/tools/ffmpeg/ORIGIN.txt) and the
  [license notice for the referenced build](App/tools/ffmpeg/LICENSE).

WIT and FFmpeg executables are not included in this repository.

## Game content

Fire Emblem and the supported games belong to Nintendo and Intelligent Systems.
This independent project does not include game discs, extracted artwork, fonts,
music, dialogue archives, or game executables. File layouts, identifiers, and
behavior descriptions are documented for interoperability. Users supply their
own game files.
