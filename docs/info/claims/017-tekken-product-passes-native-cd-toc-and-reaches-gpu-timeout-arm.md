---
id: C017
kind: claim
status: holds
created: 2026-08-27
tags: gpu,product,runtime,t3-04,vsync
depends: game/core/gpu_sync.cpp#GpuSyncProtocol::arm, game/core/gpu_sync.cpp#GpuSyncProtocol::poll
reconfirmed: 2026-08-27
verified_at: 2026-08-27
---

## Claim

On the selected Tekken 3 SLUS_004.02 product built against psxport `3c342ec3`, native CD and TOC
ownership reaches ResetGraph without guest VSync; the next ownership boundary is linked GPU timeout
armer `FUN_8007E8F0`, whose VSync(-1) result is only a 240-field deadline for paired poller
`FUN_8007E924`.

## Evidence

Isolated PID `3216829` opened the real CHD, printed `ResetGraph:jtb=80098b70,env=80098bb8`, and trapped
the protected VSync call at return PC `0x8007E900`. Its exact chain is
`8007E8F0 <- 8007E154 <- 8007C528 <- 800B07C8 <- 800B07A8 <- 800B07A0 <- 800B0794 <- 800B0788
<- 800B0548`. Retained instruction evidence and Ghidra independently show the arm/deadline and paired
poll-count/reset semantics. The native owner can call both authenticated original guest bodies through
the runtime dispatcher, and its hermetic test
produces both non-expired and expired/reset answers. The process exited itself and is absent; it
produced no frame, present, or audio sample.

## What would falsify it

Falsified if process-audit evidence shows PID `3216829` overlapped another game instance, the saved
log does not contain the stated ResetGraph/VSync chain, executable identity differs from
`fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c`, or independent decoding shows
either GPU function uses VSync for behavior beyond the recorded timeout clock.

## Re-confirmed 2026-08-27 — complete measured GPU caller domain

Ghidra's reference database reports five calls to `FUN_8007E8F0` and ten to `FUN_8007E924`, covering
the resident driver-table DMA, image transfer, command queue, and DrawSync paths. The three adjacent
SDK functions that inline the same clock have zero selected-executable references. ResetGraph mode 0
and driver initialization contain no VSync; direct display init `FUN_800B0954` is separately owned.
