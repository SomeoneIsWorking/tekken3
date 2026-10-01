---
id: 20
title: The card's blocker is the CD completion chain, and the sector dispatch is armed but never runs
status: open
symptom: the product presents the NAMCO PRESENTS card indefinitely; `0x800A069F` stays 1 in every run while mode is 2 and phase is 8
state_items: S003
tags: tekken3,cd-completion,blocker,sector-callback-dispatch
created: 2026-09-29
updated: 2026-09-29
---

## Answer

**The blocker is the CD completion lifecycle, and hop 2 is armed but never driven.** Decoded from the
authenticated executable, `0x800A069F` has 4 readers and 5 writers and the sector-callback slot
`0x8009B8D0` has 6 readers and 1 writer. The card is not waiting on the controller port.

`game/core/loader_lifecycle.h` is the recovery and `tests/loader_lifecycle_contract.cpp` pins 15 of
15 of its instructions against the image words. The causal chain, in order:

```c
// 0x8006C1A4 — the guest STARTS a read and ARMS the card's wait byte, in one breath.
sb   $v0,7($s1);              // *(0x800A069F) = 1        <- the card now waits
jal  0x8008F08C;              // submit to the CD chain
//   delay slot: addiu $a3,$s3,-15764  ->  $a3 = 0x8006C26C   the completion callback

// 0x8006C26C — the chain's completion callback. This is not a clock question.
void ChainCompletion(uint8_t eventClass) {
  if (eventClass == 2) {                          // 0x8006C278  bne $a0,2
    InstallSectorCallback(0x8007C2A0, -1);        // 0x8006C288  jal 0x80091F38
  }
}

// 0x80091F38 — installs the per-sector callback into a RECORD at 0x8009B8C8.
//   0x80091F78  sw $v1,-0x18($s0)   ->  *(0x8009B8D0) = the callback      THE SLOT
//   0x80091FA0  sw $s1,($s0)        ->  *(0x8009B8E8) = 1                the flag

// 0x80092034 — the per-sector handler, with $s1 = 0x8009B8C8:
lw    $a3,8($s1);      // 0x80092110   $a3 = *(0x8009B8D0)   THE SLOT, LOADED
beqz  $a3,skip;        // 0x80092118
jalr  $a3;             // 0x8009213C   CALL THE SECTOR CALLBACK   <-- hop 2

// 0x8006C2A0 — the sector callback, class 1. The ONLY writer that clears the card's byte.
void SectorCallback(uint8_t eventClass) {
  if (eventClass != 1) return;              // 0x8006C2C0
  ConsumeSector();                          // 0x8006C2E0  jal 0x80091FBC
  *(uint8_t *)0x800A069F = 0;               // 0x8006C2EC  sb $zero,7($s2)   <-- CLEARS IT
}
```

So the card clears itself only through `0x8009213C`, and the two hops are `0x8006C26C` (chain
completion, delivered) and `0x8009213C` (the sector dispatch, **never delivered**).

## MEASURED AT RUN TIME — the slot is armed, the byte is still up

One disc-backed process, read over the loopback control channel at **1,054,867 presented frames**,
3 consecutive samples unchanged:

| word | value | what it says |
|---|---|---|
| `0x800AE204` mode | **2** | not mode 3 |
| `0x800AE224` phase | **8** | the card's phase |
| `0x800A069F` wait byte | **1** | still waiting; the sector callback's clearing write has not run |
| `0x800A069E` busy byte | **0** | the loader is NOT mid-read |
| `0x8009B8D0` callback slot | **`0x8006C2A0`** | **the sector callback IS installed** |
| `0x8009B8E8` registration flag | **1** | and registered |
| `0x8009B8C8` record state | `0xFFFFFFFF` | the value `0x80091F6C` stores |
| `0x800A06B8` chain link | `0x800A0698` | the record the loader is pointing at |

Guest execution at the same point: `calls=1159458 translated_blocks=1956 executed_blocks=697286435
executed_instructions=4167259337 host_dispatches=365462 faults=0`, and
`fallback: calls=0 refused_calls=0 compilation_failed=0 self_modifying_code=0` — the JIT is the
execution path and is not silently degrading.

Two deductions follow from those words:

- **The guest is not in `FUN_8006BEA8`'s inner spin.** That loop is `0x8006BEE4 lbu $v0,6($v1)` /
  `0x8006BEEC bnez`, spinning while `0x800A069E` is non-zero and falling through to `0x8006BEFC`,
  which clears the card's byte. The live reading is `0x800A069E == 0` with `0x800A069F == 1`, so the
  byte would already be clear if the guest were there.
- **Hop 2 is armed and unused.** The per-sector handler `0x80092034` is armed into a slot at
  `0x80091F7C` by a call to `0x8009268C`, and no run has yet shown that slot being driven.

## Not established

- **Where the guest actually is.** Not measured. Read the PC through the control channel's `guest`
  denominators and a per-PC walk over a run; `budget_exit: exits=6 pc_in_code_image=6` shows the exit
  PCs are all inside the code image, which is the one hint the existing run already gives.
- **Whether delivering the dispatch clears the card.** The chain is recovered from bytes and every
  link pinned, but no run has reached the dispatch, so "the card leaves" is unmeasured.
- **How many sectors the card's read needs.** `0x80092034` re-arms on a counter at `+4($s1)`, so the
  callback is a per-sector loop and the count is not recorded.
- **The controller port.** Whether the pad is also wrong is still open; that the CD chain is the
  current blocker does not make the pad correct.

## Falsifier

1. `tests/loader_lifecycle_contract.cpp` reporting fewer than 15 of 15 pins. Today: 15 of 15.
2. A disassembly of `0x80092110` that is not `lw $a3,8($s1)` over `$s1 = 0x8009B8C8`. Today:
   `0x8E270008` and `0x2631B8C8`, pinned.
3. A run in which `0x800A069F` falls to 0 while `0x8009B8E8` is nonzero, which would mean the card
   was never waiting on the CD chain at all. **Not observed in any run so far.**

## Ruled out

- **"The card waits on the controller port"** (issue 0019). That conclusion rested entirely on
  `0x800A069F` having 0 readers. It has 4.
- **"The sector callback is installed into a slot nothing dispatches."** `0x8009B8D0` has 6 readers
  and one of them, `0x8009213C`, is a `jalr` through the value loaded from it four instructions
  earlier.