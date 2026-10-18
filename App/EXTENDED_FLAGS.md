# Extended event flags — implementation status

**Not yet an installable game patch.** The host storage contract, save codec,
save-editor display/editing, separate-storage hub router generator, and generated
native flag-bank core are implemented. The native routines are instruction-tested,
but are not installed by hub setup.
Existing hubs still use the original global-flag implementation. Do not create an
`extended_flags.json` in a playable project yet: builds, script writes, and hub
installation intentionally reject it until the complete runtime is verified.

## Agreed behavior

- Support FE9 US, EU and JP; require fresh playthroughs, without save migration.
- Store all hub state outside the vanilla 96 flags.
- Provide 1,024 extra campaign bits and 256 extra local bits for the active chapter.
- Select extended storage explicitly; do not automatically spill vanilla flags.
- Reset local state on a fresh visit; restore it on checkpoint/part resumes.
- Leave existing vanilla registrations and slot allocation unchanged.

## Implemented contract

`formats/extended_flags.py` provides immutable `FlagLayout` / `FlagEntry` models
and a mutable `ExtendedState`. The JSON manifest has `version`, `identity` (a
nonzero UUID), and `entries` with `name`, `scope`, `slot`, `chapter`, and `deleted`.
Scopes are `campaign` and `chapter`; all manifest entries use extended storage.
Chapter slots are independent per chapter. IDs are append-only and deletions
reserve their IDs. Renaming keeps the ID. `require_compatible` checks edits
against the previously installed layout, including attempted slot moves/reuse.
The UUID stays stable for compatible additions and renames. Incompatible changes
need a new UUID and playthrough. Runtime installers must persist the previous
layout separately before accepting changes; that installer is not implemented.

The format keeps ordinary `global` / `regist` / `get` / `set` / `clr` syntax.
The generated native registration hooks consult embedded scoped name tables;
the codec alone does not change what the game does with those calls.

The extension record follows the existing `T  T` payload in card saves:

| Record offset | Bytes | Meaning |
|---|---:|---|
| `0x00` | 4 | `XFLG` |
| `0x04` | 2 | Big-endian format version, 1 |
| `0x06` | 2 | Big-endian payload length, 164 |
| `0x08` | 16 | Layout UUID |
| `0x18` | 4 | Hub state |
| `0x1C` | 128 | Campaign bits, least-significant bit first |
| `0x9C` | 32 | Chapter bits, least-significant bit first |

Total record size: **188 bytes**. Hub byte 0 uses bit 0 for ACTIVE and bit 1 for
STARTED; byte 1 is destination, byte 2 pending chapter, byte 3 reserved zero.
The 18 existing `HUB_*` names alias those bits; no alignment flags are needed.

The proposed block versions are `FE8J/0x54460101` (US/JP) and
`FE8X/0x54460102` (EU). SYSF retains its retail format. These version constants
are implemented in the host codec, **not patched into any retail executable**.
Missing/truncated records, unknown versions, reserved control bits, and incorrect
block sizes become read-only undecoded blocks. The app preserves their raw bytes.
Valid extension records survive ordinary save edits and variable-sized unit-list
changes. Retargeting to a fresh chapter clears only extended local bits.

The save editor shows hub aliases and extended flag values. It uses names only
with a matching project UUID, otherwise shows set bits by numeric slot. Bulk
chapter-flag clearing requires a matching manifest to avoid clearing globals.

## Engine findings and remaining work

Run `python App/tools/audit_extended_flag_hooks.py` from the repository root.
It verifies retail DOL hashes and reports 24 functions for each region. Regional
function-map candidates and source-sized masked comparisons are **not proof of
correct regional function boundaries or safe patch sites**.

1. **Native core is generated and instruction-tested; boot validation remains.**
   `game_code/extended_flag_runtime.py` generates code and tables at `0x803A0000`.
   It rejects section/BSS overlap, exhausted text slots, and modified hook bodies.
   The `OSSetArenaLo` hook clamps the arena above the image before `OSInit` clears
   RAM. Scoped registration, full name/hash comparison (including collisions and
   Shift-JIS), get/set/clear, distinct boot/new-game/local resets, hub aliases, and
   foreign-table fallback are tested for all three regions. Separate live masks
   prevent accessing names that have not been registered. `build_core` returns
   proposed edits and an image without mutating the executable; it is deliberately
   not an installer. Dolphin cold boot and arena/heap behavior remain unverified.
2. **Writer fragments are implemented; complete save integration remains.**
   Record I/O uses byte copies for unaligned streams and a caller-supplied hard
   end address. Reads validate the complete header, UUID, and reserved hub bits
   before changing active state. Failure leaves both state and cursor unchanged.
   The preflight counts all 159 unit slots, including retail faction filtering
   and its skill exception, without moving units. It returns the required block
   size or failure. `extended_flag_file_save.py` connects it to the US/EU file
   writers before any target block is touched. The failure branch sets the card
   insufficient-space error and takes the save process's label-99 path. The
   append hook runs after terrain serialization and before CRC finalization;
   unexpected append failure bypasses finalization and card-write scheduling.
   `extended_flag_checkpoint.py` provides corresponding checkpoint guards and
   append hooks in all three regions, using their distinct frames and block
   registers. Tests cover exact capacity boundaries and untouched target blocks.
   These builders return proposed edits only; they are not production installers.
   US file-save writer
   `0x801E1CB4` clears a `0x4000` block but constructs its stream with capacity
   `0x100000`. App-side bounds checks do not prevent native overwrite. Validate the
   final size before writing any target bytes. The current serialized layout is
   3,558 bytes with empty unit slots, and each occupied slot adds 141 bytes.
   Adding the extension changes the file-block limit from 90 to **89** occupied
   records and checkpoint limit from 149 to **147**. Larger saves must fail safely
   under the agreed fixed-block-size policy; they must never be truncated.
   The US file-save process at `0x80299E10` runs the deferred writer and then
   unconditionally dereferences its output at process `+0x54`. A failed preflight
   cannot merely return: the implemented guard takes the label-99 error path before
   `extract_and_start_background_process` (`0x801E21B0`). Automatic checkpoint
   callers use separate flows: `0x80072B6C` displays a close-error dialog, while
   `0x8009EA14` and `0x800B6F48` only close the card. Those paths still require
   regional caller verification and capacity-specific user-facing messages.
   Japan's file-save writer has a different ABI: `(card context, file slot,
   parent process)`, and creates its own blocking child after serialization.
   Its verified extent is `0x374` bytes, not the US/EU `0x360`.
   `extended_flag_jp_file_save.py` now handles that ABI separately: preserve all
   three arguments on entry, return a card error without starting a child on
   overflow, and append the record before finalization. The menu's state `0x268`
   reads the card result and displays `FM_ERR_SAVE` on failure before returning
   to state `0x25D`. Native instruction tests exercise that dispatch and dialog
   branch, as well as the 89/90-record limit and append failure. Caller windows
   and the status getter are guarded against unexpected executable changes.
3. **Regional save hooks are unfinished.** The missing map entries have been
   recovered through corresponding call edges: EU save finalization `0x801E6FD8`
   (1,720 bytes), JP checkpoint writing `0x801DD57C` (780 bytes). The audit records
   these candidates and checks their final return instructions. They differ in
   size from US; map recovery alone does not verify their safety. Verify all
   version checks, CRC handling, and graceful failure paths before making edits.
   `extended_flag_container.py` now proposes a separate card filename for each
   layout. It replaces the existing filename in place, preserving all its callers
   and the surrounding strings: `X` followed by nine Base32 characters from a
   hash of the UUID. All regions fit this ten-character name. The full UUID is
   checked on open, including in the unlikely event of a shortened-name collision.
   Compatible layout edits retain the filename. These edits are still gated.
   `extended_flag_new_game.py` now adds guarded new-playthrough writer hooks in
   all regions. Capacity is checked after party initialization and before gameplay
   serialization. The free block's header has already been initialized; failure
   sets the card error and skips CRC finalization and card-write scheduling.
   Tests exercise the 89/90-record boundary and bounded extension appending.
   `extended_flag_versions.py` proposes audited block-version edits: 51 checks
   each in US/EU and 45 in JP, plus construction and finalization sites. The
   separate SYSF date stays retail. The finalizer trampoline preserves registers
   and CR0 because subsequent system-data handling reuses them. Tests inventory
   every negative date comparison and execute the edited comparison windows.
   Virtual-card support is deferred by user request and is not a release
   prerequisite for normal-card support. The retail
   virtual-card initializer (`0x801E3014` US) creates three kind-2 placeholder
   blocks with no serialized payload; changing their version alone cannot make
   them valid extended saves. Its bypass of the ordinary asynchronous card-open
   path remains unsupported; do not describe this as Dolphin memory-card support.
   `extended_flag_candidate.py` composes all normal-card fragments for each region
   and applies them to a private in-memory executable copy after validating every
   fragment and rejecting overlapping edits. It records the input hash and layout
   UUID. Tests reverse every edit and remove the injected section to recover the
   original executable exactly. This builder writes no project files and does not
   enable the production patch.
4. **Snapshot and card-load fragments are implemented; live validation remains.**
   `extended_flag_snapshot.py` captures a separate RAM shadow after `AllPush`
   finishes serialization, then restores it after `AllPop` restores party data.
   The shadow contains both the extended record and live-registration masks,
   belongs to the retail snapshot buffer pointer, and is consumed on restoration.
   Boot/new-playthrough reset invalidates it; ordinary local reset preserves it.
   Instruction tests cover tutorial chapter changes, registration restoration,
   mismatched buffer owners, and consumed snapshots in all three regions. No
   extra bytes are added to the retail snapshot buffer or card format. Actual
   tutorial execution, retry, and cold-load ordering still need Dolphin tests.
   `extended_flag_load.py` walks all eight physical card blocks before retail
   block selection. It validates bounded chunk traversal, variable unit-record
   sizes, regional magic/version, full layout UUID, and reserved hub bits without
   changing game state. Invalid/free blocks and consumed partial copies retain
   retail handling. An incompatible occupied block sets a card error and takes
   the existing card-opening process's label-99 path; valid input still goes
   through retail selection and CRC checking. A separate shared-deserializer
   hook restores extended state after party data, preserves live registrations,
   and invalidates any previous tutorial snapshot. It requires the earlier
   pre-selection guard. Unexpected in-memory corruption after validation still
   cannot be rolled back by the retail void reader; the guard is mandatory.
   US resume modes 1, 2, and 5–7 deserialize once to identify the chapter, run
   chapter startup (which resets locals), then deserialize again. Preserve that
   ordering; a read before startup alone loses restored local bits.
5. **Project/UI integration is unfinished.** The compiler now accepts an explicit
   `FlagCompileContext(layout, chapter)` for validation. It requires each active
   assigned flag to be registered exactly once, rejects registered tombstones and
   chapter-local hub aliases, and counts only unassigned names against the vanilla
   budget. It does not change emitted bytecode or automatically spill flags into
   another bank. Extended compilation treats a full vanilla bank as an error;
   callers without a context keep existing behavior. Project writing remains gated.
   The executable candidate builder accepts an optional hub chapter, installs the
   chapter-flow dependency in its private copy, and replaces legacy hub routing
   with routing to the dedicated four-byte state. It preserves other successors,
   detects conflicting code/padding, and supports an existing hub only at the same
   chapter. Tests execute the resulting router in every region and verify vanilla
   flag bytes remain untouched. Installation is still blocked by the regional
   release gate pending Dolphin acceptance checks.
   `extended_hub.py` prepares migration of an existing legacy hub. It verifies
   the saved registration layout, removes only standalone generated padding
   registrations, retains the eighteen functional aliases, and validates every
   supplied chapter against explicit bank assignments. Padding referenced by
   custom logic causes refusal. Configuration version 3 records extended storage
   and the layout UUID instead of legacy slot indexes. This is a fresh-playthrough
   migration, not a conversion of existing saves.
   The project preparation entry point combines six proposed outputs: DOL,
   startup CMB, startup sidecar, hub configuration, layout manifest and installation receipt. It snapshots
   inspected inputs and checks for stale files before returning; no files are
   written. Tests check matching UUIDs across outputs, preservation of unrelated
   registrations and scripts, the C18 budget, and refusal after an input changes.
   `project_transaction.py` now stages replacements and checksum-protected recovery
   copies under an exclusive project journal. It rechecks inputs, atomically replaces
   individual files, and rolls back ordinary failures. The group of files is not
   filesystem-atomic: interrupted transactions require recovery before further edits.
   Recovery validates all targets and refuses to overwrite later external edits or
   use damaged recovery data. A failed rollback retains its journal for a later retry.
   The commit entry point includes first-original backups in the same transaction
   and remains blocked for all unapproved game regions. Build/script guards reject
   projects with an outstanding journal, even before a manifest has been written.
   Fresh hubs can now be prepared directly with `prepare_fresh_project_update`.
   Shared setup validation checks map bounds, avatar deployment, destinations and
   dialogue, then generates scripts with explicit bank accounting and no padding.
   The proposal includes compiled scripts and sidecars, messages, optional avatar
   placement, executable, configuration, manifest, and an updated draft if one
   exists. It snapshots relevant game data, maps, deployments and scripts to reject
   stale inputs. Commit remains gated. A real-US-asset integration test covers
   C18's 58 local registrations plus two explicitly extended flags, while retaining
   all 18 hub aliases and only 30 vanilla globals; the legacy setup refuses the
   same fixture for exceeding capacity. This is host-side validation, not Dolphin.
   The native section now embeds its canonical manifest, generator revision and
   region. Installation receipts record original/replacement hook bytes. Status
   verification restores a private copy and regenerates the candidate, comparing
   owned code and metadata rather than trusting a receipt hash alone. Compatible
   updates retain the layout UUID, existing slots and unrelated flow overrides.
   Game-code saves verify these dependencies before writing; changing the hub's
   story successor, removing its routing or removing required hooks is refused.
   `prepare_reconfigure_project_update` validates the installed extended hub and
   prepares scripts, messages, configuration and runtime in one transaction. Moving
   activation to another chapter removes the previous generated activation event.
   The real-US-asset test verifies reconfiguration is read-only until applied,
   aliases remain unique, the original successor is retained and status still matches.
   `extended_project.py` handles compatible layout/script updates atomically.
   Ordinary script edits retain the executable when the layout is unchanged.
   File snapshots and directory inventories detect changes made after preparation.
   A persistent OS file lock serializes commits and recovery, and project opening
   offers recovery or cancellation before editors load an interrupted installation.
   The flag editor displays storage and physical slots, separate bank budgets and
   an explicit bank selector. New flags default to Extended for verified projects.
   Banked Excel exports carry the UUID, bank and slot; imports reject reassignment
   and validate all additions before one commit. Legacy imports retain existing
   assignments and treat new names as vanilla.
   Hub controls now select Vanilla or Extended storage, defaulting new hubs to
   Extended and retaining existing legacy choices. Installed extended hubs cannot
   be downgraded. Status distinguishes verified runtime installation from conflicts.
   `prepare_install_project_update` dispatches fresh installation, reconfiguration,
   or legacy migration plus edited setup as one proposal. The real-asset migration
   test checks padding removal and activation-event relocation together.
   Extended flags can be renamed or deleted through the editor. Renames update
   parsed literal flag operands and event labels, preserving unrelated strings,
   comments, UUID and slot. Deleting an unused flag leaves a permanent tombstone.
   References from event logic block deletion. Dynamic references, or shared-script
   references to a chapter-scoped flag, require manual review and block automatic
   edits; the editor does not guess their target scope. Vanilla/engine/hub flags
   cannot use these extended rename/delete operations.
   Remaining editor work includes visual UI checks. Save-capacity error presentation still needs validation at every
   caller. Production activation remains blocked for all three regions.
6. **Dolphin validation is not done.** Verify cold save/reload and hub round trips
   in all three regions, the chapter-17 sequence (`C18` internally), two new local
   flags, a fixture exceeding vanilla capacity, and safe over-capacity refusal.
   `tools/prepare_extended_flag_playtest.py` now prepares isolated experimental
   CISO images and Dolphin profiles without enabling production installation.
   It refuses an existing output directory. US/EU fixtures activate an added hub
   after the prologue; JP contains runtime probes only because its ChapterData
   editor is read-only. Manual Visit probes in C01 and the US/EU hub write, read
   and clear 100 campaign plus 80 chapter flags. Other ordinary story chapters
   have two extra local registrations. No probe initializes its state automatically.
   `tools/inspect_extended_flag_playtest.py` reads isolated GCI saves without
   changing them and reports CRC, UUID, hub bytes and probe counts. Templates
   include launch instructions, expected results and a test report form.
   Prepared local artifacts: `workspace/extended-flags-playtest` at repository root.
   Packaged DOL bytes match all three verified candidates. DolphinTool extracted
   eight startup/probe scripts from the images byte-for-byte; full US image
   verification reported only CISO's low-severity missing-disc-size warning.
   These are packaging checks, not successful boot or persistence evidence.
   First USA user test found working local writes/clear and checkpoint persistence,
   but campaign probes stayed clear and hub entry crashed at `0x80166278` after
   saving. The experimental exporter had bypassed `sync_system_archive()`: retail
   startup and ChapterData inside system.cmp shadowed edited loose files. Revision
   2 syncs/verifies the boot archive, preserves the test UUID/cards, and adds 2x
   animations plus turn-one automatic victory in connected test chapters. The
   corrected build still needs in-game confirmation. Regression coverage now
   checks the archive copies, not only the loose files or packaged DOL.

`game_code/extended_flags.py` intentionally has no approved regional patch edits
and is not registered in the production patch catalog. The project-level guard
rejects opted-in projects before writes instead of silently compiling extended
registrations into an unpatched game. It also verifies executable/manifest/receipt
agreement for approved regions; the approval set remains empty until the above
work passes.

## Verification

Run from `App`:

```text
python -m unittest tests.test_project_transaction tests.test_extended_hub tests.test_extended_flags tests.test_extended_flag_compile tests.test_extended_flag_runtime tests.test_extended_flag_file_save tests.test_extended_flag_jp_file_save tests.test_extended_flag_candidate tests.test_extended_flag_checkpoint tests.test_extended_flag_new_game tests.test_extended_flag_versions tests.test_extended_flag_snapshot tests.test_extended_flag_load tests.test_extended_flag_container tests.test_cmb tests.test_cmb_fe10 tests.test_save_file tests.test_event_flags tests.test_hub tests.test_chapter_flow tests.test_game_code tests.test_project
python -m unittest tests.test_extended_flag_installation tests.test_extended_project tests.test_extended_recovery tests.test_extended_flag_excel
```

Tests cover slot identity and tombstones, malformed manifests/payloads, regional
save codec round trips, variable unit records, checksums, local-only resets,
separate-state PowerPC hub routing for every regional successor target, and
refusal to apply the incomplete patch. Core tests also exercise native record I/O,
failed-read atomicity, exact capacity boundaries, faction filtering, arena clamps,
and preserved nonvolatile registers. Native instructions run in a minimal PowerPC
interpreter; the preflight's external retail skill predicate is modeled at its
ABI boundary. These tests are not Dolphin acceptance testing.
