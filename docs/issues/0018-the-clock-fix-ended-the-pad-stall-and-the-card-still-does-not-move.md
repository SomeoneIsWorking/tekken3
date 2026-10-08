---
id: 18
title: The in-segment clock fix ended the pad stall — and the card still did not move
status: open
symptom: the pad wait loop returns and the product runs tens of thousands of fields, but 0x800A069F is still 1 in every sample
tags: cd,completion,clock,dead-end
created: 2026-09-28
updated: 2026-09-29
---

**Dead end, kept so the clock is not blamed again.** The guest clock now advances inside a segment:
the pad wait loop returns in 6,526 cycles through one segment and the product runs past 25,030 fields
with `faults=0` and zero interpreter fallback. The card still does not move, so the CD completion was
never a clock question. Issue 0020 supersedes this issue's frontier table.

**The CD chain facts this established, still current.** The guest's loader sets the wait byte and hands
`FUN_8008F08C` a completion callback in one breath (`0x8006C1A4: sb v0,7(s1)`, delay slot
`addiu a3,s3,-15764` giving `$a3 = 0x8006C26C`), and `FUN_8006C26C`'s class-2 branch at `0x8006C288`
installs the sector callback `FUN_8007C2A0`, whose `0x8006C2EC` is the only writer of `0x800A069F` to
zero on this path. Owner: `game/cd/cd_protocol.cpp`, whose `cdControl` and `cdQueueStart` overrides
complete each operation inline and never invoke the registered callback.