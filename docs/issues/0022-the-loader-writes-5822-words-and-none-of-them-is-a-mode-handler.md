---
id: 22
title: The loader writes 5,822 words, and none of them is a mode handler — so 0050's interior-word case is not on the mode path
status: open
symptom: psxport issue 0050 measured that an interior-word write cannot revoke a translated block, and this loader writes code into RAM at run time
state_items: S003
tags: tekken3,invalidation,interior-word,loader,measured-absence
created: 2026-09-29
updated: 2026-09-29
---

## Question

`psxport/docs/issues/0050` measured that `lightrec_invalidate(addr, len)` only revokes a block when
the write hits that block's **first** word: an interior-word write is reported, counted in
`ExecutorCounters::invalidations`, and has **no effect**, so the stale block keeps executing.

**Is Tekken 3 exposed to that on the path of reaching a fight?** The loader writes code into RAM at
run time, so the question is real — but it is not answered by "the loader writes code". It is
answered by asking whether the written region overlaps something that was **already translated**, and
specifically whether any overlap lands on a block's first word rather than an interior one.

## Measured, from a live capture at the card

`scratch/raw/cdchain_fixed_ram.bin`, a 2 MiB guest RAM dump from a disc-backed run that reached mode 2
phase 8, compared word-for-word against the authenticated executable.

| quantity | value | denominator |
|---|---|---|
| placement cursor `*(0x800A3B88)` | `0x80128894` | — |
| window words non-zero | 112,141 | 115,712 (96.9%) |
| **window words DIFFERING from the disc** | **5,822** | 115,712 (5.03%) |
| contiguous runs those differences form | 610 | — |
| region the writes cover | `0x8012867C..0x80130668` | 32,748 bytes |
| **mode handlers inside that region** | **0** | 20 handlers |
| mode handlers at or above `0x800C0000` | 11 | 20 |

**So the loader did run and did write — 5,822 words is not a zero — and every one of them lands in a
region that no mode-dispatch target occupies.**

## A CORRECTION I MADE MID-MEASUREMENT, because it would have INVERTED the finding

The first pass read the **20 entries of the mode table at `0x80010000`** and found all 20 below
`0x800C0000`, which said *"no mode handler is ever dispatched into the window"* — and that would
have been **wrong, and wrong in exactly the direction that makes the card look solved.**

Those table entries are the **`jal` STUB addresses**, not the handlers. A mode's real handler is the
**`jal` target inside its stub** at `0x80028C94 + i*0x10`. Resolving all 20:

| modes | handlers | region |
|---|---|---|
| 0, 1, 2 | `0x800B0708`, `0x80052CC4`, `0x8004FA60` | disc text |
| 7, 8, 10, 11, 16, 18 | `0x80050318`, `0x80050428`, `0x80055590`, `0x80052520`, `0x800501C0`, `0x8004FF74` | disc text |
| **3, 4, 5, 6, 9, 12, 13, 14, 15, 17, 19** | `0x800DB1B8`, `0x800DB5B4`, `0x800DDE64`, `0x800D3228`, `0x8010FF4C`, `0x800EEE8C`, `0x800EF92C`, `0x800F0458`, `0x800F18E8`, `0x800C2434`, `0x800FF0C4` | **window** |

**11 of 20 — exactly the number issue 0016 recorded, confirming the runtime-written handler
window is real.** The gap was one level of indirection: the table holds the stubs, and the handler is
a `jal` further on. `game/frame/finite_frame.cpp`'s `kModeFunctions` and its `0x80028C9C + mode*0x10` return-PC
formula are the *stub* arithmetic, which is why the port's own dispatch never named a window address.

**The generalisable error, and it is the same shape as the ten dead taps:** a table read as the thing
it points at. `0x80010000` is a table of *pointers*; read as a table of *values* it gave 20 disc-text
addresses and a clean "0 handlers in the window" — precisely the number that would have let this
investigation stop. **Mode 3, the handler the card is blocking, is `0x800DB1B8` — in the window.**

## What that does and does not establish

**Established:** the mode-dispatch path is not exposed to 0050's interior-word case **from mode 0's
loader run**, and that is a measurement with a denominator rather than an argument. It also explains
something issue 0016 recorded and could not account for: mode 0's loader "ran to completion without
writing a single word to any handler address". The two agree — the 5,822 writes went to
`0x8012867C+`, which is **vertex/CLUT data**, and the 11 window handlers sit at `0x800C2434` through
`0x8010FF4C`, which is a different part of the window entirely.

**NOT established, and it is the part that matters for the blocker:**

1. **Whether the OTHER six loaders write into the handler window.** Six placement sites other than
   mode 0's are known and only mode 0's has been observed. **This is the exposure that counts**: the
   11 window handlers have no bytes
   from the disc and no bytes from mode 0, so one of the six *must* place them, and whichever does is
   writing into a range that the mode-3 dispatch will execute. If that write lands interior to a block
   already translated, 0050 bites, and the owner of the fix is the Lightrec fork, not this title.
2. **Whether any of that region was translated at all.** A block's span lives in Lightrec's block
   cache, which psxport does not expose, and issue 0050 says explicitly that widening the range
   psxport-side cannot help because psxport does not know where blocks start. **This issue therefore
   cannot answer the overlap question from outside the executor**, and does not pretend to. What is
   measured is a bound on where the writes are, not a proof that they were harmless.
3. **Whether the 11 window handlers are ever dispatched to at all.** If the card never leaves mode 2,
   mode 3's `0x800DB1B8` is never executed and was never translated — which would make 0050 irrelevant
   *and* would mean the card must be cleared before the window is even a question. That ordering is
   worth stating: **the card comes first, and this issue's answer only becomes load-bearing once the
   card is past.**

## Falsifier

- A mode handler inside `0x8012867C..0x80130668`. Today: **0 of 20**, with the 11 window handlers
  named individually above.
- A window-handler word differing from the disc in this capture. Today: 5,822 words differ elsewhere
  in the same window and **0 at any handler address** — so the zero is not "the capture is blank".
- Any of the six other loaders observed placing code at a window handler. **Not observed, and this is
  the measurement that would turn this issue from a bound into a finding.**

## Method note

The comparison is a whole-window word-for-word diff against the authenticated executable, not a
search for a marker. A marker search would have found the same 5,822 words and would also have
reported the same 0 at the handlers — but it could not have distinguished "the loader never wrote
here" from "the loader wrote here and the bytes happen to match the disc", and the second is exactly
the case where a marker search reports a confident zero. **The diff answers the question; the marker
search would have restated it.** And the handler list came from resolving each stub's `jal`, because
reading the stub TABLE as if it held handlers produces the same zero for the same wrong reason.

That class of error — a table read as the thing it points at, or a base propagated in only one
register — was this image's repeated failure mode. It cost one wrong writer census and one wrong
reader census before the constants above were right, which is why every address here is decoded from
the instruction words rather than carried over from a previous reading.
