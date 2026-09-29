---
id: 21
title: Six errors in a hand-assembled guest body, and the framework exonerated
status: resolved
symptom: `tekken3_mode_call_budget_resume` failed: the synthetic spinning body executed ~25k instructions per field and the counter it wrote every iteration stayed 0
state_items: S003
tags: tekken3,test-fixture,hand-assembly,load-delay-slot,override-differential
created: 2026-09-29
updated: 2026-09-29
---

## Answer

**RESOLVED. The test is GREEN, the framework is EXONERATED, and the cause was the fixture.** Six
errors were found in a 16-word hand-assembled guest body, and only the sixth explains the symptom:
the body consumed a `lw` result on the very next instruction, which an R3000 does not allow.

This issue originally read the symptom as possibly a **framework synchronisation defect** — that
Lightrec keeps translated-block stores somewhere and syncs them at a segment boundary. **That was
wrong, and it was refuted by reading the framework**, which I should have done before naming it as
one of two live possibilities. There is no second RAM buffer and therefore no memory sync that could
be defective. The lesson is recorded below in the same terms as the ten dead taps: *a hypothesis
raised from a symptom is not a measurement, and the cheapest measurement was the one not taken.*

**The frame-loop change the test exists to justify is CORRECT and is kept.** `FrameLoop::step`
dispatched every mode body except mode 0 through the non-suspending `guest::call`, which aborts on
`budget-exhausted`, and mode 2 (`0x8004FA60`, the loader) legitimately outlives a display field.
Routing all of them through `BoundedCall` is right, and the test's own `arm=control` still shows the
non-suspending entry aborting on the same body, so the two entries remain distinct.

## THE SIX ERRORS, and why the first five all looked right

The body is MIPS written by hand. **It was wrong six times, and the first five each produced a
PLAUSIBLE mnemonic**, which is why a review of the rendered text would have passed every one.

| # | written | meant | why it looked right |
|---|---|---|---|
| 1 | `0x1000FFFF` | `b -7` | a branch offset is the 16-bit field sign-extended from (PC+4), so -7 is `0xFFF9`; `0xFFFF` is -1, a one-instruction self loop |
| 2 | `0x8C2B0698` | `lw $t3,0x698($t1)` | the base register is bits 25..21 and that word carries `rs=1` ($at), not 9 ($t1). A four slipped in the register field |
| 3 | `0x1000FFF9` | `b -7` | op 0x04 is `beq`, not 0x02 `b` — and `beq $zero,$zero` IS an unconditional branch, so **Capstone prints it as `b`** |
| 4 | `0x0800FFF9` | `b -7` | op 0x02 fixed, but that makes it a `j`, whose field is `target >> 2` and **absolute**, not a PC-relative offset. It decoded as `j 0x8003FFE4` — into the scratchpad |
| 5 | `0x272A0698`, `0xAC220000` | `addiu $t1,$t1,0x698`, `sw $v0,0($t1)` | the register fields again, in a diagnostic written specifically to *prove* the store was reachable |
| 6 | **no `nop` after a `lw`** | the body as described | **not a field error at all.** Every word decodes exactly as intended and the program still misbehaves, because an R3000 does not make a load's result readable until the next instruction retires. See the RESOLVED section |

**Error 4 is the one the workspace already has a scar for.** `megamanx4` shipped five wrong call
targets from a hand-decoded listing, every one of them by treating a J-type target as
PC-relative, and every wrong value was a *plausible* guest address. The same mistake, the same
review-survivability, in a different repository and a different file. The loop-back must be
`0x08013E9A` = `j 0x8004FA68`, confirmed against `psxport/tools/disasm.py`.

**The generalisable rule, and it is the fourth time this shape has cost this workspace a defect:
compare the FIELDS, never the rendered mnemonic.** Error 3 is the sharpest case — the wrong
opcode produced the *correct mnemonic* in the framework's own disassembler, so only a field
comparison could see it. Error 4 is the sharpest the other way — the encoding was right and my
*decoder* was wrong twice, reporting a correct word as broken, which is the same trap in reverse
and is recorded because the response to a check that is wrong about a right subject is to edit the
right thing.

**The fifth thing is not in the fixture.** With the body correct and its back-edge verified by the
framework's own disassembler, the body runs **24,696 instructions and 3,528 blocks per field**,
`$t2` (the byte it spins on) reads `1` so its `beq` is not taken, and yet **`$t3` — the register its
`lw`/`addiu` write on every single iteration — reads 0.** Deleting the `beq` entirely, so the
counter path cannot possibly be skipped, changes nothing. The store at `0x8004FA7C` is not landing
in the `Core` memory the test reads, while the same `Core` sees a host-side `mem_w32` immediately
(verified: writing `0x5A5A5A5A` to the same address and reading it back returns `0x5A5A5A5A`).

**This is a framework question, not a title one**, and `psxport` is read-only here. It is either
(a) Lightrec keeps translated-block stores in its own state and the `Core` copy is synchronised only
at a service boundary, in which case a *guest* store is legitimately invisible mid-field and this
test's assertion is simply wrong about where to look; or (b) a guest store to main RAM inside a
tight loop is genuinely dropped, which would be a serious executor defect and **would bear directly
on the real card**, whose whole problem is a guest store (`0x8006C2EC sb $zero`) that never lands.
**I could not distinguish (a) from (b) from inside this repository**, and guessing which one it is
would be exactly the kind of unmeasured claim this workspace keeps paying for.

## RESOLVED 2026-09-29 — the framework is EXONERATED, and the cause was a load delay slot

**The framework has no memory synchronisation to be defective, and the cause was my fixture.** Both
halves are now measured, not assumed.

**The framework, checked directly in `psxport` (read-only here):**

1. `LightrecExecutor::memoryOps()` sets `.sb .sh .sw .lb .lh .lw .lwu .swu` and **no `direct_ram`**,
   so Lightrec has no pointer that could bypass the ops. Grepping the executor for `direct_ram`,
   `lightrec_set_ram` and `ram_ptr` returns 0 occurrences.
2. `storeWord` writes into `Core` **in the callback itself** —
   `impl.commitDeviceClock(lightrec, address); impl.core.mem_w32(address, value);` — so a store
   retires into `Core` at the moment it executes, not at a segment boundary.
3. `copyLightrecToCore` copies **registers only** (GPRs, lo/hi, pc, CP0, GTE), and that is complete
   because there is no RAM state held elsewhere to copy.

**So there is no second RAM buffer and no sync to perform. The hypothesis this issue raised —
"Lightrec syncs translated-block stores only at a service boundary" — is REFUTED, and it was
refuted by reading the framework, which I should have done before naming it as one of two live
possibilities.**

**What the store observer then settled, because the observer reports the store's own resolved
target and the values around it.** Armed on the body's `sw`:

    observer: pc=0x8004FA7C word=0xAD2B0698 base=0x800A0000 disp=1688 => address=0x800A0698 value=0x00000000
    observer: target[0] before=1500 after=1500 lastTarget=0x800A0698 distinct=0
    observer: gprs at the store: t0=0x800A0000 t1=0x800A0000 t2=0x00000001 t3=0x00000000

**The store ran 1500 times and landed on exactly the right address. It stored 0 because `$t3` was 0
at that moment — and `$t2` is 1, so the `beq` was not taken, so the `lw` at index 6 had not
delivered.**

**THE CAUSE: a missing MIPS load delay slot.** The body read the counter with `lw` and consumed it
on the very next instruction. On an R3000 a load's result is not readable until the following
instruction retires, and `lightrec/emitter.c:364` says so in as many words: *"Never handle load
delays with local branches."* Adding the two delay slots makes the counter reach 1400 and the test
pass.

**The retail body this fixture imitates does not do that**, which is the part worth keeping:
`FUN_8006BEA8` puts a `nop` after **every** load (`0x8006BEB0/BC/C0`, `0x8006BED4/D8`, `0x8006BEE4/E8`),
and the card's wait byte is written by `sb` and cleared by `sb` — **no `lw` feeds either**. So the
real `0x800A069F` path never had this hazard, and this was never a candidate for the card.

**This was the only one of the six errors that a decoder CANNOT see**, because every word decoded
exactly as intended. That is why it is now the negative case: `misScheduledBodyStoresNothing` builds
the body with the delay slot deleted, runs it, and requires the store **not** to land. It does not
(`counter=0x00000000`), so the live counter assertion in `resumeArm` can fail, and the correct body
is what makes it pass.

## THE OVERRIDE DIFFERENTIAL — run, and it FAILS, and here is exactly why

Every override this repository installs was run through the gate landed in psxport `c777c320`, built
against a private checkout of that commit so the shared tree was not disturbed:

    cmake -S . -B build/diff -DCMAKE_CXX_COMPILER=clang++ -DPSXPORT_DIR=.../psxport-pin
    heavy.py --kind build -- make -C build/diff -j2
    heavy.py --kind run -- env PSXPORT_OVERRIDE_DIFF=Tekken3::cdSync,Tekken3::cdReady,\
      Tekken3::cdQueueStart,Tekken3::cdQueueResult,Tekken3::cdCommand \
      PSXPORT_OVERRIDE_DIFF_REPORT=scratch/diff/od2.json ... ./build/diff/bin/tekken3_port
    uv run --frozen python external/psxport/tools/port/override_differential_gate.py \
      scratch/diff/od2.json --require Tekken3::cdSync

    override-differential gate: FAIL (6 failure(s), 3 key(s))

| override | seen | sampled | match | mismatch | incomparable | reason |
|---|---|---|---|---|---|---|
| `Tekken3::cdSync` @`0x80083904` | 1 | 1 | 0 | 0 | **1** | original path performed platform-service @`0x800859A8` |
| `Tekken3::cdQueueStart` @`0x80090F78` | 1 | 1 | 0 | 0 | **1** | original path performed platform-service @`0x800859A8` |
| `Tekken3::cdQueueResult` @`0x80091328` | 1 | 1 | 0 | 0 | **1** | original path performed platform-service @`0x800859A8` |
| `Tekken3::cdReady` | 0 | 0 | — | — | — | never called in this run |
| `Tekken3::cdCommand` | 0 | 0 | — | — | — | never called in this run |

A separate run also sampled `Tekken3::cdControl` @`0x80083E4C`, and it is incomparable for a
**different and more interesting reason**: `original did not return: budget-exhausted at 0x80084060`.
That address is `jal 0x800859A8` with `$a0 = -1` — the original **re-enters guest dispatch and does
not come back inside one field**.

**`0x800859A8` is this title's declared libetc `VSync`** (`game/core/vsync_field_clock.h`:
`kEntry = 0x800859A8`, and `game/core/sync_native.cpp` publishes it through `PlatformHlePlan::vsyncAddress`).
Issue 0138 is explicit that a BIOS/platform-HLE service on the original makes the call
**INCOMPARABLE** and that all-incomparable is a failure — so **this gate cannot pass for these five
overrides as they are declared, and that is a real result rather than a gap in the evidence.**

**What it means, stated precisely:** every one of these CD overrides **calls `VSync` on the original
path**, and this title answers `VSync` through `PlatformHle` precisely because the native frame
driver owns cadence and guest code must never advance the host clock through libetc VSync
(`sync_native.cpp`'s own header says so). The two facts are consistent and jointly make the
differential inapplicable to the CD overrides: the thing being compared is a body that waits on a
field the port owns, and the port will not let it run live.

**The next step is therefore NOT to weaken the gate.** It is to decide which of these five actually
need to be native overrides at all, and to own the behaviour in C++ in a form the differential can
compare — which means removing the `VSync` call from the *native* side (it already is absent) and
establishing whether the ORIGINAL's `VSync` can be given a replayable answer. That is a question for
the psxport owner, because a platform-HLE service is unreplayable by design and only they can say
whether a declared `vsyncAddress` may be treated as replayable traffic. **Not attempted here.**

## What is landed and green

- `tools/census_word.py` and `tools/probe_card_state.py`, both with working controls in both
  directions (see issue 0020).
- `game/core/loader_lifecycle.h` and `tests/loader_lifecycle_contract.cpp` — **15 of 15** recovered
  instructions pinned to the image words, and the test is **green**.
- The `mode_call_budget_resume` fixture's four encoding errors, all fixed, with a decoder check that
  caught a fifth (`jr $ra` written with `rt=31`, i.e. `jalr`) the moment it was added.

## Not established

- **Whether the CD overrides can EVER pass the override differential.** They cannot as declared, and
  the reason is structural rather than a gap in evidence: every one's original calls libetc `VSync`,
  and issue 0138 makes a platform-HLE service on the original **incomparable by design**. Deciding
  whether a declared `vsyncAddress` may be replayed is the psxport owner's call, not this
  repository's. **Not attempted here, and the gate is left failing rather than weakened.**
- **`cdReady` and `cdCommand` are unexercised.** 0 calls in a 30,000-field run, so the differential
  has no evidence about them at all. A longer run, or a run that reaches the code path that calls
  them, is what would sample them.
- **Whether Tekken 3 is exposed to issue 0050's interior-word stale-block case.** Named as the next
  question, not answered. The question is whether the loader writes into a range Lightrec has already
  translated, and if so whether the overlap lands on a block's first word (safe) or an interior word
  (stale execution). Answering it needs a live capture and the executor's own counters **from one
  process**, and it was not obtainable while another title held the product slot.

## Falsifier

1. `tekken3_mode_call_budget_resume` going red with the body unchanged. Today: **green**, with the
   counter at 1400 after 8 fields, and the mis-scheduled negative at 0.
2. `perturbedProgramsAreRejected` accepting any of its five field perturbations. Today: 5 of 5
   rejected.
3. `hostWriteToTheSameAddressIsVisible` failing to read back its own sentinel. Today: passes.
4. `docs/issues/0020`'s census selftest failing. Today: pins found, negatives absent.
