---
id: 20
title: The card's blocker is the CD chain after all — two of issue 0019's refutations were DEAD TAPS
status: open
symptom: `0x800A069F` is reported to have 0 readers and the sector-callback slot 0 readers, which redirects the blocker to the controller port
state_items: S003
tags: tekken3,dead-tap,census,cd-completion,blocker,recovery
created: 2026-09-29
updated: 2026-09-29
---

## Answer

**Issue 0019's two refutations are wrong, and both were zeros from an instrument that could not
report anything else.** Decoded from the authenticated executable, `0x800A069F` has **4 readers and
5 writers**, and the sector-callback slot `0x8009B8D0` has **6 readers** — not 0 and 0. The card's
blocker is the CD completion lifecycle, exactly as issue 0018 said, and issue 0019's parking note
parked the fix on the strength of the two zeros.

**This is the TENTH dead tap in this workspace, and the first one produced by a census rather than
by a counter.** The previous nine all returned a convincing **zero**. This one returned a convincing
zero too — but the decisive number, the sector-callback slot, is a *match count of zero* on a word
that the guest demonstrably loads and calls, and that is the same error in the same shape as
`megamanx4`'s `0x0113D7D0`.

## THE INSTRUMENT, AND WHY IT REPORTED ZERO

`tools/census_word.py`, written to answer this and pinned so it cannot. It walks the text once in
address order carrying 32 register constants, and it does **not** reset them at branch targets,
because constants live in registers and survive basic blocks. Two separate things were wrong with
the census that produced the refutation:

1. **IT FOLLOWED THE WRONG REGISTER.** This image builds a global the way every MIPS compiler does:

   ```asm
   8006BEAC  lui   $v0,0x800A      <-- the constant lands in $v0
   8006BEB4  addiu $s0,$v0,0x698   <-- and is CONSUMED in $s0
   8006BEBC  lbu   $v0,7($s0)      <-- the reader, at 0x800A069F
   ```

   A sweep that only propagates `lui rX` / `addiu rX,rX,imm` **in the same register** sees no address
   at all. Across a whole image written that way this is not an edge case, it is the dominant idiom,
   and it makes the sweep report **0 readers for essentially every global in the image**.

2. **IT LOST CONSTANTS ACROSS BRANCHES.** Cutting the walk at a branch target and restarting from an
   empty register file discards every cross-block constant. The per-sector handler in this very
   image keeps `$s1 = 0x8009B8C8` live across ~40 instructions and four branch targets — and it is
   the handler that dispatches the sector callback.

**The zero was therefore not a measurement of absence. It was a measurement of the sweep's own
register model.** The two numbers issue 0019 reports as evidence (`0` for `0x800A069F`, and `no
instruction reads 0x8009B8D0`) are exactly the two numbers this class of sweep always produces.

## MEASURED — WITH DENOMINATORS, AND WITH A CONTROL IN BOTH DIRECTIONS

    scanned 295,936 / 295,936 words of text at 0x80010000..0x80131000
             (loaded from file offset 0x800 to t_addr — the PS-X EXE sector rule)
    classified 8,392 address-forming accesses with a constant base

| word | issue 0019 said | measured | of |
|---|---|---|---|
| `0x800A069F` | 0 readers | **4 readers, 5 writers** | 295,936 walked |
| `0x8009B8D0` | "no instruction reads that word" | **6 readers, 1 writer** | 295,936 walked |
| `0x8009B8CC` | — | 2 readers, 3 writers | 295,936 walked |

**The control is in BOTH directions, because a census that can only find things proves nothing:**

    control pin 0x800A069F: 4 reader(s), 5 writer(s)  (require >=1/>=1) ok
    control pin 0x8009B8C8: 5 reader(s), 4 writer(s)  (require >=1/>=1) ok
    negative     0x8001FFF0: 0 reader(s), 0 writer(s)  (require 0/0) ok
    negative     0x800B8D5B: 0 reader(s), 0 writer(s)  (require 0/0) ok

The negatives are addresses this image demonstrably does not name, and they stay at 0. **A sweep
that can produce both a confident non-zero and a confident zero is measuring the image; one that
only ever answers "nothing" is measuring itself.** The main path REFUSES to print a verdict if the
pins do not hold, so a broken sweep cannot report a subject count at all.

## THE RECOVERED LIFECYCLE, IN READABLE C++ TERMS

`game/core/loader_lifecycle.h` is the recovery, and `tests/loader_lifecycle_contract.cpp` pins all
**15 of 15** of its instructions against the image words. The causal chain, in order:

```c
// 0x8006C1A4 — the guest STARTS a read and ARMS the card's wait byte, in one breath.
sb   $v0,7($s1);              // *(0x800A069F) = 1        <- the card now waits
jal  0x8008F08C;              // submit to the CD chain
//   delay slot: addiu $a3,$s3,-15764  ->  $a3 = 0x8006C26C   the completion callback

// 0x8006C26C — the chain's completion callback. Nothing about this is a clock question.
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
jalr  $a3;             // 0x8009213C   CALL THE SECTOR CALLBACK   <-- hop 2, and it is REAL

// 0x8006C2A0 — the sector callback, class 1. This is the ONLY writer that clears the card's byte.
void SectorCallback(uint8_t eventClass) {
  if (eventClass != 1) return;              // 0x8006C2C0
  ConsumeSector();                          // 0x8006C2E0  jal 0x80091FBC
  *(uint8_t *)0x800A069F = 0;               // 0x8006C2EC  sb $zero,7($s2)   <-- CLEARS IT
}
```

**So the root cause of the card in one sentence:** the guest sets `0x800A069F` and registers
`0x8006C26C` in the same breath, and the only code in the image that clears that byte
(`0x8006C2EC`) runs inside a sector callback the guest installs at `0x8009B8D0` and dispatches at
`0x8009213C` — so the blocker is the completion lifecycle, and the two hops are `0x8006C26C` (chain
completion, **delivered and measured** by issue 0018) and `0x8009213C` (the sector dispatch, **never
delivered**, and wrongly parked by issue 0019 on a census that could not see the load).

`0x800A069F` is not read by 0 instructions. It is read by `0x8006BEBC`, which is inside
`FUN_8006BEA8` — **the function mode 2 is sitting in**, and whose inner spin at `0x8006BEE4` is an
untimed `bnez` loop on `0x800A069E` with no counter and no timeout.

## THE CONTROL ON THE RECOVERY, AND ITS NEGATIVE

`tests/loader_lifecycle_contract.cpp` is a reading, and a reading is only worth something if it can
be falsified, so every address is asserted against the image **as an encoding** rather than as a
mnemonic. This was not decoration: the first version hand-derived 15 encodings and **9 of them had
`rs` and `rt` transposed**, and the image turned all nine red at once.

| arm | result |
|---|---|
| pins | **15 of 15** recovered instructions match the image words |
| derived relations | slot = record + 8, argument = record + 16, flag = record + 32, busy = base + 6, wait = base + 7 |
| the two clearing writes | asserted to be **different addresses** — if they ever collapse, one path silently stops clearing the byte |
| mutant: one pin's immediate changed | **red**, 14 of 15, naming the address and both words |
| mutant: `kTextFileOffset` 0x800 → 0x0 (the `0xF800` sector-padding error) | **red and REFUSED** at 0 of 15, because the 0-of-N guard fires before any verdict |
| no image provisioned | **exit 77, REFUSED** — a clone without media skips rather than reporting a red it cannot earn, and a clone with media cannot silently skip |

## MEASURED AT RUN TIME — both hops are ARMED, and the byte is still up

One disc-backed process, read over the loopback control channel at **1,054,867 presented frames**
(42x the depth of any prior run), 3 consecutive samples unchanged:

| word | value | what it says |
|---|---|---|
| `0x800AE204` mode | **2** | not mode 3 |
| `0x800AE224` phase | **8** | the card's phase |
| `0x800A069F` wait byte | **1** | still waiting; the sector callback's clearing write has not run |
| `0x800A069E` busy byte | **0** | the loader is NOT mid-read |
| `0x8009B8D0` callback slot | **`0x8006C2A0`** | **the sector callback IS installed** |
| `0x8009B8E8` registration flag | **1** | and registered |
| `0x8009B8C8` record state | `0xFFFFFFFF` | the value `0x80091F6C` stores |
| `0x800A0698` chain link | `0x800A06B8` | the record the loader is pointing at |

Guest execution at the same point: `calls=1159458 translated_blocks=1956 executed_blocks=697286435
executed_instructions=4167259337 host_dispatches=365462 faults=0`, and
`fallback: calls=0 refused_calls=0 compilation_failed=0 self_modifying_code=0` — the JIT is the
execution path and is not silently degrading.

**This moves the frontier in a way nothing before it did, so it is worth being precise about what it
does and does not establish.**

- **Hop 2 is ARMED.** Issue 0018's table recorded it as "never armed, because hop 1 never ran". That
  is now stale: the callback is in the slot and the flag is set.
- **The guest is NOT in `FUN_8006BEA8`'s inner spin.** That loop is
  `0x8006BEE4 lbu $v0,6($v1)` / `0x8006BEEC bnez` — it spins while `0x800A069E` is **non-zero** and
  falls through to `0x8006BEFC sb $zero,7($v0)`, which CLEARS the card's byte. The live reading is
  `0x800A069E == 0` with `0x800A069F == 1`, so if the guest were in that loop the byte would already
  be clear. **It is not in that loop.** That is a real deduction from two measured words, not a guess.
- **So the blocker is neither the controller port (refuted above) nor the CD-chain spin, and it is
  NOT YET NAMED.** The sector callback being installed but its clearing write never running is still
  the leading candidate, and the specific open question is **what invokes the per-sector handler
  `0x80092034` at all** — it is armed into a slot at `0x80091F7C` by a call to `0x8009268C`, and no
  run has yet shown that slot being driven.

## Not established

- **Where the guest actually is.** Not measured. The next step names the instrument: the framework's
  store observer (`PSXPORT_STORE_OBSERVE`) is armed and accepts these addresses, but reports only at
  shutdown, and a shutdown has not yet been captured with the observer armed. The alternative, which
  is cheaper, is to read the PC through the control channel's `guest` denominators and a per-PC
  census over a run — `budget_exit: exits=6 pc_in_code_image=6` shows the exit PCs are all inside the
  code image, which is the one hint the existing run already gives.
- **Whether delivering the dispatch clears the card.** The chain of causation is recovered from bytes
  and every link pinned, but *no run has yet reached the dispatch*, so "the card leaves" is
  unmeasured. This issue does not claim it.
- **Whether the dispatch fires once or once per sector.** `0x80092034` re-arms on a counter at
  `+4($s1)`, so the callback is a per-sector loop; how many sectors the card's read needs is not
  counted here.
- **The controller port.** Issue 0019's SIO measurements are **not** refuted by this issue — they
  were taken from a different question and nothing here touches them. Whether the pad is *also*
  wrong is still open, and the CD chain not being the current blocker does not make the pad correct.

## Falsifier

Each of these would make this issue wrong, and each is a measurement:

1. `tools/census_word.py --selftest` reporting 0 readers for either control pin, or a non-zero
   reader for either negative. Today: pins found, negatives absent.
2. `tests/loader_lifecycle_contract.cpp` reporting fewer than 15 of 15 pins. Today: 15 of 15.
3. A disassembly of `0x80092110` that is not `lw $a3,8($s1)` over `$s1 = 0x8009B8C8`. Today:
   `0x8E270008` and `0x2631B8C8`, pinned.
4. A run in which `0x800A069F` falls to 0 while `0x8009B8E8` is nonzero — which would mean the card
   was never waiting on the CD chain at all. **Not observed in any run so far.**

## Ruled out

- **"The card waits on the controller port."** That conclusion rested entirely on `0x800A069F`
  having 0 readers. It has 4.
- **"The sector callback is installed into a slot nothing dispatches."** `0x8009B8D0` has 6 readers
  and one of them, `0x8009213C`, is a `jalr` through the value loaded from it four instructions
  earlier.
