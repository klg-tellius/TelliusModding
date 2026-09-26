# How Path of Radiance finds a message by ID

Confidence: **confirmed** (US `main.dol`, static disassembly).

- A dialogue file (`Mess/cNN.m`, `common.m`, …) is a *relocatable resource*, the same container family as models and other data. Its header gives the pointer-table offset (+04), a relocation count (+08, zero for message files) and an export count (+0C). The export table is the list of `(text offset, ID offset)` pairs, so every message ID, such as `MS_02_OP_01`, is an exported symbol.
- When the file loads, every export is registered in the engine's single global name table. The same table also holds sound cues and script scene names. It has 509 buckets, chained, with up to 10,240 entries.
- An event script plays a message with `TalkEvent("MS_02_OP_01")`. The engine resolves the ID through that table, then starts the message window with the text.
- The table stores two numbers per name: a bucket hash (each byte × 37, mod 509) and a check hash (each byte × 31). Bytes are treated as signed. A lookup walks the bucket and returns the first entry whose check hash matches. The name itself is never compared.
- Consequences:
  - The order of messages inside a file does not matter. Vanilla files happen to be sorted alphabetically by ID.
  - Two different IDs whose bucket and check hashes both match would shadow each other, and the one loaded first wins. No two vanilla message IDs collide.
- Text whose first character is `@` is treated as a template: `@{0}`…`@{9}` are replaced by runtime values (names, numbers) before display.

Functions (US): `load_relocatable_resource` 8003F87C, `register_scene_info_by_name` 8000D3EC, `hash_lookup_by_name_a` 8000D354, `resolve_ui_string_template` 8000E0E4, `script_TalkEvent_handler` 800BAF1C, `start_message_window_process` 8011D908.
