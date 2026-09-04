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

Capture the loader's request, command, callback pointer/class, event state, destination range, and
terminal result across the card-to-menu boundary in an independent retail run and the native/Lightrec
product. The diagnostic must report candidates scanned and both the reached and not-reached answers.
Implement only the first measured missing owner, then rerun the same bounded boundary; do not add a
delay, phase write, or scene-pointer shortcut.
