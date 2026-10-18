---
id: "crash-assertions-diagnostics"
title: "Crash, Assertions & Diagnostic Output"
description: "How FE9 reports invalid resources and engine state, and how to turn those traces into reproducible debugging evidence"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Debugging", "Engine"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/crash-assertions-diagnostics.md"
system_entries: ["FE9-SYS-014", "FE9-SYS-375"]
system_reviewed: ["FE9-SYS-014", "FE9-SYS-375"]
system_reviewed_with_gaps: []
system_reviewed_by: "Claude Opus 5.5"
system_reviewed_on: "2026-10-15"
system_known_gaps: []
system_gap_work: []
---
# Crash, Assertions & Diagnostic Output

FE9's retail executable retains development diagnostics: assertion text, source paths and line references, build timestamps, author metadata, resource-loader errors, state complaints, and console-style messages. These strings are useful evidence about what rejected an input, but they are not a substitute for validating the resource and tracing the caller that supplied it.

## Mental model and worked example

Treat a diagnostic as the last labelled checkpoint before failure. It can identify the subsystem and violated assumption; the call path and inputs explain why the assumption failed. A message mentioning a missing section does not prove the archive is globally corrupt: the container may be valid while the caller requested a misspelled or absent section name.

For example, suppose a modified chapter crashes immediately after loading its map archive. First reproduce from the same clean save and capture the final messages. If the last diagnostic names a map section, compare the request string, archive directory, section size, and decompression result with an unmodified chapter. Then follow the caller into the consumer that interprets the section. Fixing the section name or record shape is safer than patching out the assertion, because later code still relies on the condition it checked.

## Diagnostic system boundary

<span id="fe9-sys-014"></span> Diagnostics sit across subsystems rather than owning gameplay. Resource managers report failed files, archives, sections, allocations, and decodes. Script/event code reports impossible call or state conditions. Platform and renderer/audio layers can report failed operations. Assertions additionally preserve development provenance such as source file, line, function, author, timestamp, or build context.

The output is evidence with several possible consequences. A check can log and continue with a fallback, reject the current operation, return an error to its caller, enter a debugger-oriented halt, or lead to a fatal crash when no recovery exists. The presence of assertion text in the binary does not by itself show that a retail path executes it or that every runtime environment exposes the text through the same sink.

## Inputs and owned state

A diagnostic site receives the values available at the failure boundary: requested resource identity, section name, pointer/result status, counts and indices, state flags, script arguments, platform return values, or object identity. Static strings may add the source location and a human explanation. Global debug facilities, build configuration, emulator logging support, and exception handling determine where the message can be observed.

The failing subsystem still owns the underlying state. Logging a bad unit slot does not make the logger the owner of unit allocation; an archive assertion does not own archive layout. This distinction prevents a common research error in which nearby debug strings are treated as the implementation of the system they describe.

## Rules and lifecycle

1. A subsystem validates an operation or receives an error from a lower layer.
2. The diagnostic site formats or selects a retained message and optional provenance.
3. The active output path writes to an available console, log, debug overlay, or exception context.
4. Control follows that site's policy: continue, fall back, reject/return, halt, or crash.
5. The investigator correlates the message with the caller, concrete inputs, and the first invalid state.

Modders should record the first failure, not only the final crash. A malformed resource can trigger secondary complaints after a loader has already returned an invalid object. Repeating the test from a stable save and changing one input at a time separates a deterministic validation failure from timing, memory, or stale-state noise.

## Severity, recovery, and safe use

Do not infer severity from wording alone. “Error” can precede a recoverable fallback, while a terse failed invariant can stop the process. Confirm the control-flow edge after the diagnostic call and whether the caller checks a returned null/error. Likewise, a string with a source line is evidence of an assertion macro at build time, not proof that a retail console is visible.

Patching out checks is hazardous. Assertions often guard bounds, allocation results, object types, resource sizes, and lifecycle order. If the invariant is genuinely too strict for a mod, update the producer, consumer, and validated limit together. If the error is expected and recoverable, preserve a clear failure return and test cleanup/retry behavior.

## Retail logging and assertion paths

<span id="fe9-sys-375"></span> The retail executables contain three distinct mechanisms, and their retained strings must not be treated as one console:

- `debug_console_printf` (`0x800056CC`) is disabled. Its byte-identical `0x54`-byte US, PAL, and Japanese body only saves the variadic argument registers, sets return register `r3` to zero, restores the stack, and returns. It never calls a formatter or output primitive. The US/PAL/Japanese executables contain 432/430/427 direct calls respectively, covering script diagnostics, database and chapter loading, combat/EXP dumps, animation/resource complaints, debug menus, memory-card timing, audio cues, and developer viewers; every one is silent and control continues exactly as if a zero-returning stub had been called.
- `report_assertion_failure` is active and has exactly 57 direct call sites in each retail build. Its `0x34`-byte wrapper has the same structure in all three regions, forwarding source filename, line, and assertion text to the build's assertion handler. Those sites are concentrated in placed-object, `GActor`, skeleton/animation, material, shape, camera, and actor-material rendering code. The handler (`0x8005B010`) never returns. It walks up to 16 stack frames and formats the message with `vsprintf`, but it sends the stack trace, the message and the file/line only to the disabled `debug_console_printf`, so no text reaches the screen or any log. It then loops: each frame it reads the pads, copies the embedded framebuffer to an external framebuffer with the clear flag set, and presents it. After the first copy the buffer holds only the clear colour, so the retail result is a **black screen with no error text**. At most one partly drawn frame can appear first. The loop ends only through the standard soft reset: holding exactly Start+B+X for 30 consecutive frames, or pressing and releasing the console Reset button. The handler then waits for GX to drain and calls `OSResetSystem` with a code derived from the video-mode flags. While bit `0x100` of `script_state_flags` is set, the loop ignores both inputs and the console stays frozen. The same chord-and-button logic runs every frame in normal play (`debug_input_state_init`, `0x8005AE78`), so the soft reset behaves the same with or without an assertion. An assertion is not a recoverable log call, even though the caller's decompile shows instructions after it.
- SDK `OSReport` is also active. Its region-mapped `0x80`-byte implementation builds a variadic argument list and calls `vprintf`; exactly 95 direct calls exist in each build. Ordinary users such as initialization banners, DVD warnings, script `Report`, audio/GX diagnostics, and platform status messages return after the report. Fatal owners add their own policy: `os_panic`, GPU-hang handling, DMA faults, and unhandled exceptions report context and then halt, reset, or remain in their exception path.

MetroTRK code is linked into all builds, but there is no direct call edge from `debug_console_printf`, `report_assertion_failure`, or `OSReport` to a TRK transport routine. TRK availability therefore does not turn the disabled game printer into an output sink. The static implementation and regional behavior are complete for FE9-SYS-375; whether a particular `OSReport`/`vprintf` message is captured by a specific Dolphin configuration or physical debug connection remains an environment-observation question under FE9-SYS-014.

## Implementation trail and reproducible workflow

Begin with the executable's string references and their cross-references. Classify each site by subsystem, input, message/provenance, sink, and control outcome. Follow wrapper functions until reaching the condition and the caller that supplies the rejected value. Cross-check with format validators and editor code in this repository, which can reproduce structural constraints without relying on emulator output.

A useful evidence row contains: build/region, scene, reproducible input, final good checkpoint, first diagnostic, native site/caller, affected resource/state, observed sink, recovery outcome, and fix. For hardware/emulator comparison, use the same disc image and save and note whether output appears in console capture, an on-screen overlay, an exception report, or nowhere visible.

### Controlled Dolphin sink capture

A clean PAL image was batch-booted with an isolated Dolphin user directory and only `MASTER`, `BOOT`, `CORE`, `DVD`, `OSREPORT`, `OSREPORT_HLE`, and `PowerPC` file logging enabled. The resulting `dolphin.log` proves both externally observable paths without changing the normal emulator profile:

- `OSREPORT_HLE` captured the apploader address trace and `This Apploader built Nov 10 2004 06:47:07`.
- Active `OSREPORT` lines arrived through Dolphin's EXI/IPL device and included the Dolphin OS heading, kernel build timestamp, emulated console type, `Memory 24 MB`, arena bounds, and the EXI/SI/OS/DVD/PAD/VI/CARD/DSP/GX/AR/ARQ/AI release banners.
- The game continued through boot and disc reads after those reports, confirming these ordinary report owners return rather than halt.

This observation answers the Dolphin sink question for ordinary SDK reports: with the two categories and file output enabled, they are visible in the emulator log. It does not exercise the assertion handler or any failure path; the fixture session below does.

### Failure fixtures

A second session ran four isolated fixtures on the US disc in a separate Dolphin user directory, with the GDB stub and `OSREPORT`/`DVD`/`PowerPC` file logging. Each fixture got a fresh boot. About 40 seconds in (the health-and-safety screen), the runner stopped at the entry of `pad_process_frame_input`, a clean frame boundary on the main thread. It injected one call with the link register pointing at a trap, then restored the registers if the call returned. The runner and its results are kept in `research/dolphin_fx/`.

| Fixture | Injected call | Visible result | Log | How control ends |
|---|---|---|---|---|
| Engine assertion | `report_assertion_failure("GUtil.h", 0xB8, …)`, a real assertion site in `render_placed_object` | Black screen; captures 2 s and 5 s later are pixel-identical | Nothing. The message, file, line and stack trace go only to the disabled printer | The handler loops in `assertion_handler_freeze_until_soft_reset`. Setting the soft-reset latch (as Start+B+X held for 30 frames would) calls `OSResetSystem`; the apploader runs again and the DOL is re-read from disc |
| Missing file | `load_relocatable_resource_default("zz_missing.bin")` | Game keeps running | One SDK line: `Warning: DVDOpen(): file 'zz_missing.bin' was not found under /.` | Returns at once with a **non-null** pointer. The module table gains a slot marked loaded, with size 0, one reference and a 32-byte leftover heap block, into which the archive loader stamps its signature. Any consumer then reads garbage |
| Missing script | `cm_load_script("Scripts/zz_missing.cmb")` | Game keeps running | The same `DVDOpen()` warning, with the path lower-cased in place | Returns 1 (success) and links the empty module into the live script-module chain, so later script lookups walk a bogus module |
| Heap exhaustion | `heap_alloc(Base, 0x1000000)` on the 5.2 MiB `Base` heap | Last frame stays on screen | With Dolphin's default fast memory: a run of `Invalid read/write from 0x00000010…` warnings from `0x800C5E28` onward, and the game limps on with corrupted low memory. With MMU emulation on: `Unhandled Exception 2`, then a full CPU context dump (`SRR0 = 0x800C5E28`) | The memory report prints nothing. The module purge and the retry run, then the null block header is dereferenced. On accurate emulation, the data-access exception reaches `__OSUnhandledException`, which dumps the context and halts in `PPCHalt` |

These results settle the severity question for each family. An engine assertion is fatal and silent: black screen, soft reset only. A missing file or script is not detected by the game at all. The only trace is the SDK's `DVDOpen` warning, and the failure surfaces later in whatever consumes the empty module. Heap exhaustion is fatal: on hardware, and on Dolphin with MMU emulation, it produces the SDK's unhandled-exception context dump and a halt. Dolphin's default settings hide this and continue in a corrupted state. So when testing a mod in Dolphin, turn MMU emulation on whenever you investigate a crash: a run that survives with fast memory proves nothing.

Retail hardware has no further output path. `OSReport` writes to the EXI debug channel that Dolphin emulates, and a retail console has nothing attached to it, so a player sees only the screen states in the table.

## Interactions and limits

[Developer & Debug Tools](./developer-debug-tools.md) documents hidden menus, overlays, viewers, and test harnesses. Those tools may expose or provoke diagnostics, but they are interactive development features; this page owns failure reporting and investigation. [Engine & Resource Loading](./engine-resource-loading.md), format pages, events, runtime architecture, memory, audio, and rendering remain the owners of their validated data.

Diagnostics can differ by build, region, environment, and optimization. Some strings may be retained but unreachable, several call sites may share one message, and a final exception can obscure the earlier cause. Absence of visible output is not proof that no check ran.

## Known gaps and required evidence

No known gap remains. The static behaviour, the active `OSReport` sink and the four failure families are confirmed in an isolated Dolphin session. Renderer and video failures need no separate fixture: GX FIFO setup, the GPU-hang check, VI configuration and video-mode detection call `os_panic`, which goes through the same `OSReport`-then-halt path as the exception handler. The MusyX/AX audio library (`0x80240000`–`0x80266FFF`) never calls `OSReport`, `report_assertion_failure` or `os_panic`; only its GBA DSP command helpers panic. An audio failure therefore produces no diagnostic of any kind. Whatever it does is the audio owner's own behaviour, not part of this system.

Do not patch out the checks to create evidence; preserve the rejected condition and use disposable fixtures or copies. This focused article remains the correct primary home, so no new article is currently required.
