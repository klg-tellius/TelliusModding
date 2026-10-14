---
id: "crash-assertions-diagnostics"
title: "Crash, Assertions & Diagnostic Output"
description: "How FE9 reports invalid resources and engine state, and how to turn those traces into reproducible debugging evidence"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Debugging", "Engine", "Research needed"]
aliases: []
status: "published"
last_reviewed: "2026-10-14"
sources: ["tellius-archive-research", "telliusmodding-source"]
cms_collection: "systems"
source_path: "systems/crash-assertions-diagnostics.md"
system_entries: ["FE9-SYS-014", "FE9-SYS-375"]
system_reviewed: ["FE9-SYS-014", "FE9-SYS-375"]
system_reviewed_with_gaps: ["FE9-SYS-014"]
system_reviewed_by: "Codex"
system_reviewed_on: "2026-10-14"
system_known_gaps: ["FE9-SYS-014: Active OSReport output is now captured under an isolated Dolphin profile, but safe custom-assertion and representative malformed-resource/state fixtures plus any physical-hardware observation are still missing; their exact visible recovery must not be inferred from static control flow alone."]
system_gap_work: ["FE9-SYS-014: Completed the US/EU/JP call census for the no-op game debug printer, the 57-site engine assertion path, and active OSReport/panic/exception paths; compared retained diagnostic strings, source/line metadata, DVD warnings, GX hangs, TRK separation, and post-call control. A clean PAL batch boot with Dolphin file logging captured OSREPORT_HLE apploader output and active EXI OSREPORT SDK/OS/arena banners. Isolated assertion/failure fixtures and hardware capture remain."]
---
# Crash, Assertions & Diagnostic Output

FE9's retail executable retains development diagnostics: assertion text, source paths and line references, build timestamps, author metadata, resource-loader errors, state complaints, and console-style messages. These strings are useful evidence about what rejected an input, but they are not a substitute for validating the resource and tracing the caller that supplied it.

## Mental model and worked example

Treat a diagnostic as the last labelled checkpoint before failure. It can identify the subsystem and violated assumption; the call path and inputs explain why the assumption failed. A message mentioning a missing section does not prove the archive is globally corrupt: the container may be valid while the caller requested a misspelled or absent section name.

For example, suppose a modified chapter crashes immediately after loading its map archive. First reproduce from the same clean save and capture the final messages. If the last diagnostic names a map section, compare the request string, archive directory, section size, and decompression result with an unmodified chapter. Then follow the caller into the consumer that interprets the section. Fixing the section name or record shape is safer than patching out the assertion, because later code still relies on the condition it checked.

## FE9-SYS-014 — Diagnostic system boundary

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

## FE9-SYS-375 — Retail logging and assertion paths

<span id="fe9-sys-375"></span> The retail executables contain three distinct mechanisms, and their retained strings must not be treated as one console:

- `debug_console_printf` (`0x800056CC`) is disabled. Its byte-identical `0x54`-byte US, PAL, and Japanese body only saves the variadic argument registers, sets return register `r3` to zero, restores the stack, and returns. It never calls a formatter or output primitive. The US/PAL/Japanese executables contain 432/430/427 direct calls respectively, covering script diagnostics, database and chapter loading, combat/EXP dumps, animation/resource complaints, debug menus, memory-card timing, audio cues, and developer viewers; every one is silent and control continues exactly as if a zero-returning stub had been called.
- `report_assertion_failure` is active and has exactly 57 direct call sites in each retail build. Its `0x34`-byte wrapper has the same structure in all three regions, forwarding source filename, line, and assertion text to the build's assertion handler. Those sites are concentrated in placed-object, `GActor`, skeleton/animation, material, shape, camera, and actor-material rendering code. The handler is not the no-op printer: it formats text with `vsprintf`, owns framebuffer/VI/GX and controller-input operations, performs subsystem cleanup, and reaches `OSResetSystem`. An assertion therefore transfers control into the engine's diagnostic-screen/reset path; it is not a recoverable log call merely because the caller's decompile shows following instructions.
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

This observation answers the Dolphin sink question for ordinary SDK reports: with the two categories and file output enabled, they are visible in the emulator log. It does not establish how the custom assertion screen looks or whether a physical retail console exposes the same bytes. Those require a fixture that actually reaches `report_assertion_failure` and a documented hardware capture path.

Representative test families are missing files, missing archive sections, truncated records, invalid counts/indices, allocation exhaustion, bad script arguments, impossible scene transitions, renderer/audio initialization failures, and stale object references. Each should be tested independently; deliberately corrupting multiple layers produces ambiguous evidence.

## Interactions and limits

[Developer & Debug Tools](./developer-debug-tools.md) documents hidden menus, overlays, viewers, and test harnesses. Those tools may expose or provoke diagnostics, but they are interactive development features; this page owns failure reporting and investigation. [Engine & Resource Loading](./engine-resource-loading.md), format pages, events, runtime architecture, memory, audio, and rendering remain the owners of their validated data.

Diagnostics can differ by build, region, environment, and optimization. Some strings may be retained but unreachable, several call sites may share one message, and a final exception can obscure the earlier cause. Absence of visible output is not proof that no check ran.

## Known gaps and required evidence

FE9-SYS-014 remains **reviewed with a gap**. Ordinary active `OSReport` visibility in Dolphin is now confirmed, but observation cannot yet substitute for the unrun failure families. Close it only after creating isolated, safe fixtures for a custom engine assertion and representative missing resource/section, malformed size/index, allocation failure, invalid state transition, script error, GX/renderer failure, and audio failure. Record whether the assertion screen appears and whether each owner continues, falls back, returns, halts, or resets. Physical retail/development hardware should be recorded when actually available, not treated as implied by Dolphin. `debug_console_printf` and TRK need no activation experiment: the former is a proven no-op and the three logging paths do not call the latter.

Do not patch out the checks to create evidence; preserve the rejected condition and use disposable fixtures or copies. This focused article remains the correct primary home, so no new article is currently required.
