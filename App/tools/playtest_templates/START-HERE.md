# Extended flag / hub playtest

## Return positioning update (revision 7)

The generated opening now applies the return tile immediately after deploying
the avatar, before camera focus and fade-in. It should no longer visibly teleport
when the player phase begins. Existing campaign saves and layouts are unchanged.
Restart Dolphin with the same launcher/profile you have been testing, then do a
chapter round trip. Do not restore an old Dolphin save state. In-game confirmation
of this timing change is pending.


Experimental USA, EU and Japanese builds include a hub, 100 campaign probes,
80 local probes, visible entrance markers, 2x animations and turn-one victory
shortcuts in the linked chapters. Each build has its own save layout and card.
Do not import saves from another test build. Start a new game for a fresh build.
In-game verification is still required.

## Start

1. Close any other running Dolphin instance.
2. Double-click **Play-GFEE01.cmd** for US (recommended first).
   **Play-GFEP01.cmd** is EU; **Play-GFEJ01.cmd** is JP. Only requested regions have launchers.
3. Start a **new game**, preferably Normal with tutorials enabled for the first run.
   If prompted to create a game save on the memory card, accept.
4. Complete the prologue normally. All regions should enter the test hub afterwards.

Each launcher forces a separate Dolphin user directory. Slot A is a normal
emulated memory card, stored as GCI files inside that directory. Your normal
Dolphin saves/settings are not used. Controller mappings were copied; configure
the controller in this isolated Dolphin if yours does not work. Cheats are off.
Do not move these test saves into your regular Dolphin profile.

## Manual probe tiles

The prologue and the hub both have three **Visit** actions. Coordinates
are zero-based from the top-left of the map; the tiles have no special artwork.
The prologue opening moves Ike away from his deployment tile; use the coordinates
below, not his position after the opening. In the hub, the avatar starts on WRITE.
READ is one tile to its left; CLEAR is two tiles left.

| Tile | Coordinate | Visit action |
| --- | --- | --- |
| WRITE | (6, 7) | Sets all 100 campaign test flags and all 80 local test flags |
| READ | (5, 7) | Reports campaign and local values separately: ALL SET, ALL CLEAR, or MIXED |
| CLEAR | (4, 7) | Clears those test flags only; leaves hub routing flags alone |

Choose **Visit**, not Wait. These probe events never automatically initialize
the flags, so reload failures cannot be hidden by automatic re-setting.
The hub refreshes its avatar after actions. In the prologue, normal turn/action
limits still apply. If a tile or command cannot be reached, record that as a
fixture failure rather than guessing the result.

## First test: fresh state and persistence

- Before WRITE, READ should report campaign ALL CLEAR and local ALL CLEAR.
- Visit WRITE, then READ: both should be ALL SET.
- Make an in-game suspend/checkpoint save when that option is available. Stop
  emulation, close Dolphin completely, relaunch with the same launcher, and load
  the checkpoint. READ must still report both ALL SET. Do not use save states.
- Visit CLEAR, save/relaunch/load again, and verify both are ALL CLEAR.
- Write again before finishing the prologue. Use an ordinary file save when
  the game offers one. Cold-load that save and check the next chapter/hub.
  Campaign must stay ALL SET; a newly entered chapter's local bank must be clear.
  A pre-battle file save may legitimately restart local flags; use a checkpoint
  for the mid-map local-state test.

If suspend is unavailable in the prologue, perform that part in the hub.

## Hub round trip

The avatar looks like Ike but has a separate test identity. The hub is a flat
12 x 12 map. Destinations use **Arrive**, and **Visit** describes the destination.

| Destination tile | Destination |
| --- | --- |
| (4, 4) | Chapter 1 (internal C02): use this for the first round trip |
| (6, 4) | Chapter 2 (internal C03): use after finishing Chapter 1 |
| (8, 4) | Chapter 17 (internal C18): advanced multipart test |

1. READ on first hub entry: campaign values should match the prologue; local
   values should be CLEAR even if you set them in the prologue.
2. WRITE in the hub, then Arrive at (4, 4). Choose End on player turn 1 to finish it.
3. You should return to the hub at (5, 6), with only the dedicated avatar active.
4. READ: campaign ALL SET, local ALL CLEAR (a new chapter visit resets locals).
5. Repeat the trip and test ordinary saving/reloading while hub routing is active.

The C18 shortcut does not create a chapter-appropriate army or inventory. Use it
only after the basic round trip works; early units may not survive. All ordinary
story scripts C01-C31 include at least two additional extended local flags.
The prologue and hub have 80 local probes, in addition to 100 campaign probes,
so these builds exercise more named flags than the vanilla table can hold.

## Tutorials and failure reporting

In the prologue, try a tutorial after writing the probes. After returning from
the tutorial, READ should still show the values from before the tutorial. Also
check retry/game-over behavior where practical. Record whether the test used a
file save, checkpoint, tutorial, or chapter transition.

If the game crashes, freezes, loses a flag, fails to save, or routes to the wrong
chapter, stop that scenario and record:

- Region and chosen difficulty; exact last action and expected/observed result.
- Last working save and whether the reload was from a fully closed Dolphin.
- A screenshot of any error or mixed-values message.
- The test folder's GCI files and `test-build.json` (keep them local; they contain game data).

After closing Dolphin, run **Inspect-test-saves.cmd**. It reads the isolated GCI
files and writes `save-diagnostics.json` with checksums, layout matches, hub bytes,
and saved probe counts. It does not modify the saves. Zero GCI files means no
memory-card save has been written yet. Fill in **RESULTS.md** and send the results
and diagnostic report back in this chat.

## Not yet covered by this package

JP added-hub creation uses the Japanese 0x5C-byte ChapterData layout. This
package does not claim to test exact save-record capacity boundaries, deliberately
corrupted/wrong-layout saves, or every save-error screen. Those remain separate
acceptance checks. Never treat successful boot alone as persistence approval.
