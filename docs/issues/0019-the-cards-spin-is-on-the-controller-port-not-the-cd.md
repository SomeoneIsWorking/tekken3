---
id: 19
title: The card's spin was parked on the controller port on two zeros that were dead taps
status: superseded
symptom: the NAMCO PRESENTS card never leaves, and a note concluded the spin is on the SIO0 controller port because the sector-callback slot appeared to have no readers
tags: tekken3,dead-tap,cd,sio
created: 2026-09-29
updated: 2026-09-29
---

**Superseded by issue 0020. Kept because the shape of the error is what must not be repeated.** The
parking rested on two confident zeros from a constant-propagation sweep that propagated `lui`/`addiu`
**in the same register only** and reset its register file at every branch target. This image builds
every global the way a MIPS compiler does — `lui $v0` then `addiu $s0,$v0,imm`, built in one register
and consumed in another — and the handler that dispatches the sector callback holds
`$s1 = 0x8009B8C8` live across ~40 instructions and four branches. Re-measured: `0x800A069F` has 4
readers and 5 writers, and `0x8009B8D0` has 6 readers, one of which is `0x8009213C jalr $a3` calling
the value loaded four instructions earlier at `0x80092110 lw $a3,8($s1)`.

A sweep that only ever answers "nothing" is measuring its own register model, not the image.

**What survives:** the SIO0 measurements this issue took. They answer a different question, nothing in
issue 0020 touches them, and whether the pad is *also* wrong is still open — the CD chain being the
blocker does not make the controller port correct.