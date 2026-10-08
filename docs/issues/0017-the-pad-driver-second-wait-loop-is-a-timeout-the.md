---
id: 17
title: The pad driver's second wait loop is a TIMEOUT the port cannot expire, because RCnt2 only moves at executor segment boundaries
status: open
symptom: the product sits in FUN_80093478's second loop burning a whole per-turn budget and never returns
state_items: S003,S004,S007,S008
tags: re-first,pad,sio,rcnt2,cpu-executor,lightrec
created: 2026-09-28
updated: 2026-09-28
---

## Answer

**The loop is not waiting for hardware the port cannot deliver. It is waiting for a CLOCK, and the
loop's own timeout is armed correctly.** `FUN_80093478`'s second loop exits on either of two things,
and both are reachable; the countdown one simply never becomes true, because the only thing that
moves RCnt2 in psxport is guest instruction accounting, and that happens **once per executor
segment**, after `lightrec_execute` has already returned.

The product runs the loop inside a single segment. So for the whole 564,492-cycle budget the guest
reads the same RCnt2 value, the exit test `(RCnt2 - snapshot) >> 3 >= 0x190` is false on every
iteration, and the segment ends only when the budget is spent — after the loop has already given up.
The counter, the countdown, and the loop's code are all correct. **Where the accounting happens is
the defect, and the owner is the framework's Lightrec integration, not this title.**

## The loop, from the bytes

```asm
; 0x80093534..0x80093550 — BEFORE the loop
80093538  lw    v1,-18080(v1)   ; v1 = *(0x8009B960) = the pad-status pointer
80093540  lw    v0,0(v1)
80093548  andi  v0,v0,0x0080    ; pad-status bit 7
8009354C  bne   v0,zero,0x80093604   ; SET -> skip the second loop entirely
; 0x80093554..0x80093580 — the loop's constant operands
80093558  ori   t1,t1,0x1120    ; t1 = 0x1F801120  RCnt2 DATA
80093560  ori   a2,a2,0x1128    ; a2 = 0x1F801128  RCnt2 TARGET
8009356C  ori   t0,t0,0x1124    ; t0 = 0x1F801124  RCnt2 MODE
80093578  lw    a0,-31104(a0)   ; a0 = *(0x800A8680) the latched snapshot
80093580  lw    a1,-7640(a1)    ; a1 = *(0x800AE228) the armed threshold
; 0x80093584 — THE SECOND LOOP
80093584  lhu   v0,0(t1)        ; RCnt2 now
8009359C  lhu   v0,0(a2)        ; RCnt2 TARGET, for the wrap
800935BC  lhu   v0,0(t0)        ; RCnt2 MODE
800935C4  andi  v0,v0,0x0200    ; bit 9 selects the scaling
800935D0  sltu  v0,v0,a1        ; RAW delta   < threshold ?
800935D4  beq   v0,zero,0x80093690   ; -> give up and return
800935E0  srl   v0,v0,3
800935E4  sltu  v0,v0,a1        ; (delta >> 3) < threshold ?
800935E8  beq   v0,zero,0x80093690   ; -> give up and return
800935F8  andi  v0,v0,0x0080    ; pad-status bit 7 again
800935FC  beq   v0,zero,0x80093584   ; clear -> loop
```

Confirmed independently by `pyghidra tools/ghidra_query.py disasm 0x80093540 0x80093604`
(49 instructions, matching word for word).

**So the loop has a timeout, and returning `0xFFFF` from it is a designed outcome, not a failure.**
That is the correction to issue 0011 and issue 0016, and it changes the shape of the proposed fix: an
override that replaced only the first spin would have looked like it worked, because the second loop
would then be the only thing standing there.

`FUN_800951B8` arms it, and it is the whole of that function:

```asm
800951C0  lhu   v0,0(v0)        ; RCnt2
800951C8  sw    a0,-7640(at)     ; *(0x800AE228) = $a0
800951D4  sw    v0,-31104(at)    ; *(0x800A8680) = RCnt2
```

`0x190` is `FUN_80093478`'s own argument at `0x800934EC`, and `0x3C` is the same call inside
`FUN_800932A0`'s copy of the loop at `0x80093390`. The driver waits `0x190 >> 3 == 0x190` shifted
counts, i.e. **3,200 raw RCnt2 ticks** — about 94 µs on hardware, which is a plausible pad
inter-byte delay and is the reason the loop has a countdown at all.

RCnt2 MODE is never written by the guest (0 stores to `0x1F801124` in the authenticated text), so
bit 9 is clear, so the arm TAKEN is the shifted one. Issue 0016's "the countdown arm can never be
taken" is about the bit-9 *variant*, not the timeout; the timeout is live and is the one that runs.

## The measurement, and what each arm is for

| arm | what varies | result |
|---|---|---|
| `clock` | nothing; no guest code | **1** distinct `rootCounter2()` value over **4,096** polls with no accounting between them, **1,024** with accounting every 64 instructions |
| `bit7` | one pad-status word: bit 7 set, which the driver tests at `0x8009354C` and which SKIPS the loop | **returns**, 186 cycles, 8 blocks |
| `retail` | nothing; the product's own path and its own 0x190 | **budget-exhausted at `0x80093584`**, 564,492 cycles, 40,316 blocks, 282,244 instructions, 0 fallback, 1 segment |
| `segmented` | nothing but the segment length: same bytes, same fixture, same total allowance, handed home every 65,536 cycles | **leaves the loop** and reaches `0x800934D8`, 9 segments |

`bit7` and `segmented` are the two arms that make the answer falsifiable, and they are the reason
this is not just a story about a loop:

- **`bit7` is the control for REACHING the loop.** If setting the bit the driver tests does not skip
  the loop, the harness never exercised it and the `retail` arm's number means nothing. It returns in
  186 cycles against `retail`'s 564,492, so the harness reaches it and the stall is that loop
  specifically — not the function, not the executor, not the image mapping.
- **`segmented` is the mutant that identifies the mechanism.** Identical guest bytes, identical
  fixture, and the same total work allowance; the only difference is how often the executor returns
  to the host. One segment and the loop never ends. Nine and it does. Guest accounting is
  `accountExecutedInstructions` at `runtime/cpu/lightrec_executor.cpp:598`, which runs once per
  segment, after `lightrec_execute` returns — and `Timing::rootCounter2()` is a pure function of
  `EmulatedTime`, so inside a segment it cannot move.

`counter_entry=8192` / `counter_exit=28292` is the same fact seen from the other side: the delta is
exactly 20,100, which is `282244 mod 65536` — every executed instruction, accounted in one lump
**after** the loop was already behind. The counter moved; it moved too late.

**The `retail` arm's single segment is what the product actually does, not a fixture artefact.**
`segmentCycleBudget` is normally also capped by `hostTurnTicksUntilDue`, but `registerHostTurn` is
called by **no port in this workspace** — a grep across all ten titles' `game/` trees and the whole
psxport tree returns nothing outside `runtime/psx/boot/host_turn.cpp` itself. With no registered core,
`hostTurnTicksUntilDue` returns "no bound at all", so a segment runs the whole per-turn budget. That
is checked here rather than assumed, because if a port did register a host turn the segment would be
capped at one display field — still far longer than a guest's pad countdown, but a different number
to quote.

## The fix is in the framework, and its shape is a design decision, not a bound

`external/psxport/AGENTS.md` is explicit that an override is owned behaviour and never a repair for a missing
semantic, and the executor contract already says the right thing:

> Before a native override, HLE/device callback, interrupt/exception handoff, frame/VSync boundary,
> thread yield/exit, budget exhaustion, or fault is observed by host code, all guest-visible state
> and elapsed cycles are committed to `Core`.

**A memory-mapped register read IS a device callback, and the MMIO helpers at
`runtime/cpu/lightrec_executor.cpp:107-142` do not commit elapsed cycles.** That is the contract
violation, and it is the thing to fix. There are three candidate mechanisms and they are not
equivalent, so the choice is named here rather than taken unilaterally:

| mechanism | what it does | cost / risk |
|---|---|---|
| **(a) commit cycles in the MMIO helpers** | call `accountGuestInstructions` from `loadHalf`/`loadWord`/`store*` | **ruled out on cost.** It drags `serviceCdc()` — `cdc_drive_service`, which walks the drive event queue and may *execute a command* — into every hardware register read, on the JIT's hottest out-of-line path. It also arms the spin watchdog per access, which would start failing runs that legitimately poll hardware. |
| **(b) make the clock observable inside a segment** | give `Timing` a live guest-position source and have `emulatedCpuTicks()` include it, so RCnt2, the SIO0 `/ACK` deadlines and the CDC drive all read truthfully | the correct fix, and it fixes the whole class rather than this register. **Blocked on a units question, below.** |
| **(c) bound the segment** | cap `segmentCycleBudget`, the mechanism the framework already uses for the host field deadline | smallest change and it unblocks the title today, but it is **a bound, not the root cause**: a guest with a 10-tick countdown still sees the counter jump by the cap. It also costs a `copyCoreToLightrec`/`copyLightrecToCore` round trip every cap, and it changes throughput for all seven ports. |

**The units question is the blocker for (b), and it is the operator's call, not mine.** The
framework's clock is in *instructions*: `accountGuestInstructions` is fed
`executedInstructionCount` (`executed_instructions + fallback_instructions`), and `runtime/psx/frame/timing.h` says so
out loud — "neither counter is yet a cycle-accurate R3000 model (issue 0007)". The only live counter
Lightrec exposes is `lightrec_current_cycle_count`, which is in *cycles*, and the executor resets it
to 0 at every segment start. Measured on this very call: 564,492 cycles for 282,244 instructions,
so the two units differ by about 2x here. Adding the live cycle count to an instruction-based clock
would silently rescale every deadline in the framework — the CDC drive clock, the SIO0 `/ACK`
timings, and the field pacing — across every port. That is not a change to make blind from a
subagent with no product slot to validate it on.

If the operator wants the title unblocked before (b) is designed: **(c) is available today at a
known cost, and it is a bound, and I would mark it as one** —
`// STOPGAP: cap the segment so a guest polling a hardware counter cannot outrun the accounting
boundary, because EmulatedTime has no live source inside a translated segment and making one
correct requires choosing the clock's unit (instructions vs cycles) across every port.`

## What this does and does not establish about the CD wait

It **removes** the `FUN_80093478` override as the proposed fix. Issues 0011 and 0016 both converge on
overriding that function, and both are wrong about the shape: the loop's bound is armed by the guest
and correct, the counter is delivered and correct, and an override would have replaced a function
whose only defect is that it is reading a clock the framework stops giving it.

It **does not** say the card is fixed, and it does not contradict the retained
`scratch/probe_logs/loader_b.probe.txt` readings. Issue 0016's live samples — mode 2, phase 8, `0x800A069F == 1` for
fields 98..6865 — are consistent with this and with the product being in the pad loop, because the
pad poll runs in the VBlank handler and the CD completion path is blocked behind the same
`in_irq` wedge issue 0011 measured. **Whether releasing the pad loop is sufficient to let a CD
completion be delivered is not established here and is the next run.**

## Ruled out

- **Overriding `FUN_80093478`.** The function is not misbehaving; its clock is. This also means
  issue 0011's and issue 0016's shared proposal is superseded, and the four `jal` sites the
  `bit7`/`segmented` arms exercise are not a title defect.
- **Presetting the countdown threshold in a fixture as a mutant.** The first draft of the harness
  did exactly this, and it could not fail: `FUN_800951B8` stores its own `$a0` into `0x800AE228`, so
  the fixture's word is overwritten before the loop reads it. The arm was removed rather than
  "fixed", and the reason is recorded here because a mutant that cannot fail is this repository's
  recorded failure mode, not a hypothetical.
- **Reading `0x800A8680` as the snapshot and `0x8009E228` as the threshold.** Both were wrong on the
  first draft — the first by 0x20, the second by 0x10000 — and the tool caught both by re-deriving
  them from the instruction words and refusing on a disagreement. Issue 0016's `0x800A8680` and
  `0x800AE228` are both correct.
- **Bounding the loop, or giving `Sio0::status()` a bit the hardware does not set.** The first is a
  symptom bound; the second is forging a hardware response the guest never asked for.

## Next

1. **Decide the clock's unit** and implement (b) in psxport, in the Lightrec integration. Owner:
   `runtime/cpu/lightrec_executor.cpp` (accounting boundary) with `runtime/psx/frame/timing.*` (the clock).
2. **Then re-run this tool.** Its `segmented` arm is the forward-looking check: if (b) works, the
   `retail` arm should stop exhausting in the loop, and this tool **refuses** rather than reporting a
   pass, because "the loop exits" is a real change that needs the rest of the port re-verified
   against it. Widen `judge()` only when that is what the tool is for.
3. **Then re-measure the CD wait.** What a run must read, in this order:
   - `0x800AE228` and `0x800A8680` together with RCnt2, over **several** fields — a single sample is
     not a measurement of a per-field question, and this port submits ~1,600 primitives on odd
     frames and **zero** on even ones, so a one-field capture can miss a per-field overlay entirely.
     The endpoint's `shot` command (driven through the framework's `dbgclient.LiveClient`) is what bumps
     a chosen even frame.
   - `0x800A069F` falling to 0 with `0x8009B8E8` nonzero: the sector callback fired. That is the
     answer to whether the card is reachable, and it is the same probe.
   - `0x800AE204` leaving 2. Success is **mode 3 reached**, not mode 2 phase 9.
4. **Mode 3 is still not statically derivable.** 11 of the 20 mode handlers live at or above
   `0x800C0000`, a 115,712-word window with 0 `jr $ra` and 0 `addiu $sp,$sp,-N`; they are written at
   run time from disc-compressed resources. So a fight frame is at least one more unknown away, and
   this issue does not guess at it.

## Next step

Run the authenticated image's own loop on the shipping executor. The first arm is the image as
shipped; the second advances the guest clock inside the segment, and a segment-length mutant is what
must release the loop. No product run was made here.
