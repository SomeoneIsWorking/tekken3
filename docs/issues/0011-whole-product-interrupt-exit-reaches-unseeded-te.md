---
id: 11
title: Product stalls in the title-loader scene after NAMCO PRESENTS
status: investigating
symptom: tekken3_port presents the NAMCO card for 1,200 fields but does not reach the menu or gameplay
state_items: S004,S008
tags: runtime,cd,title-loader,t3-04
created: 2026-08-25
updated: 2026-09-04
---

## Current boundary

The current product reaches a stable presented `NAMCO PRESENTS` card, then stops making observable
title progress. The remaining discriminator is the title loader's CD request/completion state and
callback/event ownership. No evidence yet separates a missing queue completion from a title state
transition that is waiting on a different retail condition.

The authenticated `SLUS_004.02` text was re-imported at `0x80010000` from the provisioner-verified
SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` and queried
through Ghidra. This narrows one concrete loader wait but does **not** establish that the current
Lightrec product reached it. `FUN_80052A70` returns byte `0x800A069F`; its caller
`FUN_80052CC4` waits while the return is nonzero. `FUN_800529CC` starts the underlying loader:
`FUN_8006BF20` queues its asset extent, and `FUN_8006C084` sets the wait byte to `1` before
submitting command `0xA0` through `FUN_8008F08C` with request-mode argument `6` and callback
`FUN_8006C26C`. The current title CD overrides do not own that `FUN_8008F08C` command path.

The callback chain distinguishes completion from error. `FUN_8006C26C` registers
`FUN_8006C2A0` with `FUN_80091F38` only on class `2`. `FUN_8006C2A0` consumes one 0x800-byte
sector on class `1`, decrements the outstanding byte count, advances the destination, and clears
`0x800A069F` after the last queued extent. Its class-`5` error branch records loader failure state
`9` and leaves the wait byte set. Ghidra's narrow disassembly confirms the byte set at
`0x8006C1A4` and the clear at `0x8006C410`. The code makes either a missing sector callback or a
class-`5` error a possible permanent wait; only live callback/result evidence can choose between
them and a different stalled title state.

The last bounded real-CHD run completed 1,200 native fields and emitted a 960x720 sink image. Field 1
was black while display state initialized; fields 119 and 1,199 showed the centered Namco card. The
run reported no fatal, watchdog, guest VSync, or dropped layer. This proves presentation reached the
card; it does not prove the menu, gameplay, input, audio, or full title flow.

## Grounded preceding owners

- The retail entry reaches CD initialization. Getstat responses return `0x02`; retained boundary
  evidence records agreement on 34 CPU values, 38 distinct RAM bytes, and four CDC fields for the
  normal response path, including init step `0x16 -> 0x17`. That retired measurement is evidence,
  not a current product gate.
- Tekken's linked `CdSync` (`FUN_80083904`) and controller wrapper (`FUN_80083E4C`) preserve title
  validation, command/status globals, mirrors, and return ABI while delegating the hardware operation
  to psxport's synchronous stock-libcd owner.
- `FUN_80090F78` and `FUN_80091328` have one direct caller, `FUN_80091E5C`; the synchronous queue
  owner transfers the requested sectors before publishing success and never manufactures a clock or
  completion.
- `FUN_80090D88` routes blocking GetTN/GetTD through the synchronous controller and derives result
  bytes from the opened CHD's measured track metadata.
- GPU timeout armer `FUN_8007E8F0` and poller `FUN_8007E924` use `Game::timing.vblank` rather than
  guest VSync. A complete Ghidra xref census covers five armer callers and ten paired checks across
  GPU DMA, image transfer, command queue, and DrawSync.

Isolated PID `3216829` opened the real CHD, passed the synchronous directory and TOC paths, reached
ResetGraph, and exposed the GPU timeout clock at return PC `0x8007E900`. Its measured chain was:

```text
FUN_8007E8F0 <- FUN_8007E154 <- FUN_8007C528 <- FUN_800B07C8
  <- FUN_800B07A8 <- FUN_800B07A0 <- FUN_800B0794 <- FUN_800B0788 <- FUN_800B0548
```

The native timeout owner and the subsequent 1,200-field run crossed that boundary without weakening
the protected VSync trap. PID `3216829` exited and was confirmed absent.

## Ruled-out shortcuts

- Advancing a synthetic clock, raising the watchdog, or increasing the field cap would conceal the
  stalled state rather than complete the missing title transition.
- Publishing fabricated success before requested sectors are in guest RAM violates the synchronous
  read contract.
- Forcing CD state, kicking a queue manually, or bypassing callbacks would skip the lifecycle whose
  ownership is under investigation.
- The earlier inference that CD-system state had failed was too strong: a trace excluded ready state
  `1` at one sample but did not distinguish initializing state `2` from failed state `3`.

## Next discriminator

Capture `0x800AE204` (mode), `0x800AE224` (phase), loader wait `0x800A069F`, outstanding bytes
`0x800A06A4`, destination `0x800A06A8`, raw-command queue count `0x800A3E40`, callback pointer
`0x8009B8D0`, callback class, and final loader state `0x800A05D8` across the card-to-menu boundary
in an independent retail run and the native/Lightrec product. Report both reached and not-reached
answers for `FUN_8006C26C` and `FUN_8006C2A0`, including request and callback denominators.
Implement only the first measured missing owner, then rerun the same bounded boundary; do not add a
delay, phase write, or scene-pointer shortcut.
