---
id: C019
kind: claim
status: holds
created: 2026-09-28
tags: re-first,pad,sio,rcnt2,cpu-executor,lightrec
depends: tools/verify_pad_wait_exit.py, tests/pad_wait_exit.cpp
reconfirmed: 2026-09-28
verified_at: 2026-09-28
---

## Claim

In the authenticated Tekken 3 `SLUS_004.02` image, `FUN_80093478`'s **second** wait loop is a
**bounded timeout**, not an unbounded wait, and it does not exit because **RCnt2 cannot move inside
one Lightrec segment**: the runtime accounts guest instructions once per segment, after
`lightrec_execute` has returned, and `Timing::rootCounter2()` is a pure function of that clock. The
loop, the countdown and the counter are all correct. **The defect is in the framework's accounting
boundary, not in the guest and not in this title.**

## Evidence

`tools/verify_pad_wait_exit.py`, on the shipping Lightrec executor against the authenticated image.
It refuses to report until it reproduces **18/18** ground-truth instructions and re-derives the
threshold global, the snapshot global and the arm argument from the instruction words.

| arm | what varies | measured |
|---|---|---|
| `clock` | nothing; no guest code | **1** distinct `rootCounter2()` value over **4,096** polls with no accounting between them; **1,024** with accounting every 64 instructions |
| `bit7` (control) | one pad-status word: bit 7, which the driver tests at `0x8009354C` and which SKIPS the loop | **returned**, 186 cycles, 8 blocks |
| `retail` | nothing; the product's path and its own `0x190` | **budget-exhausted at `0x80093584`**, 564,492 cycles, 40,316 blocks, 282,244 instructions, **0** fallback, 1 segment |
| `segmented` (mutant) | nothing but segment length: same bytes, same fixture, same total allowance, handed home every 65,536 cycles | **left the loop**, reached `0x800934D8`, 9 segments |

The loop's own bytes, confirmed independently by
`pyghidra tools/ghidra_query.py disasm 0x80093540 0x80093604` (49 instructions, matching):

| fact | where | value |
|---|---|---|
| pad-status bit 7 skips the loop | `0x80093548` / `0x8009354C` | `andi 0x0080` / `bne -> 0x80093604` |
| RCnt2 DATA / TARGET / MODE | `0x80093558` / `0x80093560` / `0x8009356C` | `0x1F801120` / `0x1F801128` / `0x1F801124` |
| latched snapshot | `0x80093578` | `*(0x800A8680)` |
| armed threshold | `0x80093580` | `*(0x800AE228)` |
| the two exits | `0x800935D4` and `0x800935E8` | both `beq $v0,$zero,0x80093690` — the loop's own epilogue |
| the scaling selector | `0x800935C4` | RCnt2 MODE bit `0x0200`, never written by the guest, so the shifted arm runs |
| the arm | `0x800951B8` | `*(0x800AE228) = $a0`, `*(0x800A8680) = RCnt2`; `$a0 = 0x190` at `0x800934EC` |

`counter_entry=8192` / `counter_exit=28292` seen from the other side: the delta is exactly 20,100 =
`282244 mod 65536`, i.e. every executed instruction accounted in one lump **after** the loop was
already behind.

**The single segment is the product's real behaviour, not a fixture artefact.** `registerHostTurn` is
called by no port in this workspace (grepped across all ten titles' `game/` trees and the whole psxport
tree — nothing outside `host_turn.cpp` itself), so `hostTurnTicksUntilDue` returns no bound and a
segment runs the whole per-turn budget. That is checked, not assumed: if a port did register a host
turn the segment would be capped at one display field instead — still far longer than a guest's pad
countdown, but a different number to quote.

**The mutant is the claim.** Same guest bytes, same fixture, same total allowance; only how often the
executor returns home differs, and that alone decides whether the loop ends.

## What would falsify it

- `tools/verify_pad_wait_exit.py` printing `REFUSED` instead of a verdict, or any of its 14 selftest
  cases (3 image refusals, 1 accepted ground truth, 10 transcript refusals) failing.
- The `segmented` arm **also** exhausting inside the loop. Then segment granularity is not the
  mechanism and this claim's explanation is wrong. The tool refuses on exactly that.
- The `bit7` control failing to return, or costing as much as the `retail` arm. Then the harness
  never exercised the loop and the `retail` arm's number is not evidence about it. The tool refuses
  on both.
- The `clock` arm reporting **1** distinct value even *with* accounting. Then the counter does not
  move at all and "the accounting boundary" is not the explanation. The tool refuses on that too,
  because reporting it as a freeze would be a tautology.
- An independent disassembly of `0x80093584..0x80093600` disagreeing with the bytes above — in
  particular any RCnt2 MODE bit 9 write, which would change which arm the countdown takes.
- Executable identity differing from SHA-256
  `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c`.

## Limits of this claim, stated here rather than in a reader's inference

- **It does not claim the card is reachable after the fix.** It locates the stall and its mechanism.
  Whether releasing the pad loop is *sufficient* for a CD completion to be delivered is not measured
  and is the next run's question.
- **It does not propose the mechanism to implement, because the choice is the operator's.** Charging
  the clock from the MMIO helpers is ruled out on cost (it drags `cdc_drive_service`, which can
  execute a command, into every hardware register read). Making the clock observable inside a
  segment is the correct fix and is blocked on a units question: the framework's clock is in
  instructions (`accountGuestInstructions` is fed `executedInstructionCount`) while the only live
  counter Lightrec exposes, `lightrec_current_cycle_count`, is in cycles, and this call measured
  564,492 cycles for 282,244 instructions. Mixing them rescales every deadline in the framework across
  every port. See issue 0017 for the three-way table.
- **It supersedes the shared conclusion of issues 0011 and 0016 that `FUN_80093478` needs a title
  override.** It does not contradict their live measurements. The retained `loader_b.probe.txt`
  samples — mode 2, phase 8, `0x800A069F == 1`, fields 98..6865 — are consistent with the product
  being in this loop, because the pad poll runs in the VBlank handler.
- **Two of this claim's own constants were wrong on the first draft and the tool caught both.** The
  snapshot was read from `0x800A8660` and the threshold from `0x8009E228`; the real words are
  `0x800A8680` and `0x800AE228`, and the latter two are what issues 0011 and 0016 name. The tool
  derives them from the instruction words and refuses on a disagreement rather than trusting them.
- **No product run was made for this claim.** `coord/claims/product-slot/claim.md` was held by
  another agent until 2026-09-29T13:05. Every live number here is from the test-only executor run
  this repository's own gate drives, or is quoted from a retained log another agent produced.
