---
id: 14
title: The GPU-queue timeout owner was armed from a field clock nothing in this product advances
status: fixed
symptom: the native owner replacing FUN_8007E8F0/FUN_8007E924 could never time out, and the 21 real guest VSync queries aborted in the framework's protected handler
tags: runtime,vsync,gpu-timeout,binary-fact
created: 2026-09-27
updated: 2026-09-27
---

**The guest facts, kept because they are measured from the image and expensive to re-derive.**
`FUN_8007E8F0` is the linked GPU-queue timeout armer: it calls the libetc `VSync` leaf at `0x800859A8`
with `a0 = -1` (a query, not a wait), stores `field + 0xF0` at `0x80098CC4` and zeroes the poll count
at `0x80098CC8`. `FUN_8007E924` re-reads the same field word and on a **signed** `deadline < field`, or
after `0xF0000` polls, raises `GPU timeout, queue %d, stat %08x` and runs the exact reset sequence.

**A negative VSync mode never waits; it returns one word, `0x8009AC68`.** That is the guest's VBlank
field count, with exactly two writers in the whole text: the library init zeroing it at `0x8008637C`
and the per-vblank callback `FUN_800863B0` incrementing it at `0x800863DC`, installed by `FUN_80086358`
from `FUN_80085D5C`. Ghidra reports zero references to that word because it does not model the
two-register `lui`/`lw` form, so a decoded sweep is the authority for writers and Ghidra for reads.

**The defect, and its shape:** the owner read `Game::timing.vblank`, whose only incrementer this
title's finite frame loop never calls, so the clock was frozen at 0, the deadline was always `0xF0`,
and the signed poll test could never be true. The owner now reads the word the retail leaf itself
returned and the title declares it as `PlatformHlePlan::vsyncQueryCounterAddress`, so the framework's
protected VSync handler answers the guest instead of refusing it. `tools/verify_vsync_field_clock.py`
re-derives the address, both writers and the 22-site call census (21 queries, one waiting).