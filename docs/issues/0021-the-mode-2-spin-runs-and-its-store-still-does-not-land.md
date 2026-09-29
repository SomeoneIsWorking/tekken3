---
id: 21
title: The mode-2 body spins correctly and its `sw` still does not land — four hand-assembly errors found on the way
status: open
symptom: `tekken3_mode_call_budget_resume` fails: the synthetic spinning body executes ~25k instructions per field and the counter it writes every iteration stays 0
state_items: S003
tags: tekken3,test-fixture,hand-assembly,lightrec,frame-loop
created: 2026-09-29
updated: 2026-09-29
---

## Answer

**`tests/mode_call_budget_resume.cpp` is RED, and it is left red on purpose.** The test the previous
agent wrote for the frame loop's bounded mode call does not pass, and the reason is not the frame
loop. Getting to that answer required fixing **four** hand-assembly errors in its synthetic guest
body, and the fifth thing that is wrong is not in the fixture at all.

**The frame-loop change the test exists to justify is CORRECT and is kept.** The defect it was
written for is real: `FrameLoop::step` dispatched every mode body except mode 0 through the
non-suspending `guest::call`, which aborts on `budget-exhausted`, and mode 2
(`0x8004FA60`, the loader) legitimately outlives a display field. Routing all of them through
`BoundedCall` is right, and the test's own `arm=control` still shows the non-suspending entry
aborting on the same body, so the two entries remain distinct.

## THE FOUR HAND-ASSEMBLY ERRORS, and the fifth finding

The body is 12 words of MIPS written by hand. **It was wrong four times**, and each wrong version
produced a PLAUSIBLE mnemonic, which is why a review of the text would have passed all of them.

| # | written | meant | why it looked right |
|---|---|---|---|
| 1 | `0x1000FFFF` | `b -7` | a branch offset is the 16-bit field sign-extended from (PC+4), so -7 is `0xFFF9`; `0xFFFF` is -1, a one-instruction self loop |
| 2 | `0x8C2B0698` | `lw $t3,0x698($t1)` | the base register is bits 25..21 and that word carries `rs=1` ($at), not 9 ($t1). A four slipped in the register field |
| 3 | `0x1000FFF9` | `b -7` | op 0x04 is `beq`, not 0x02 `b` — and `beq $zero,$zero` IS an unconditional branch, so **Capstone prints it as `b`** |
| 4 | `0x0800FFF9` | `b -7` | op 0x02 fixed, but that makes it a `j`, whose field is `target >> 2` and **absolute**, not a PC-relative offset. It decoded as `j 0x8003FFE4` — into the scratchpad |

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

## What is landed and green

- `tools/census_word.py` and `tools/probe_card_state.py`, both with working controls in both
  directions (see issue 0020).
- `game/core/loader_lifecycle.h` and `tests/loader_lifecycle_contract.cpp` — **15 of 15** recovered
  instructions pinned to the image words, and the test is **green**.
- The `mode_call_budget_resume` fixture's four encoding errors, all fixed, with a decoder check that
  caught a fifth (`jr $ra` written with `rt=31`, i.e. `jalr`) the moment it was added.

## Not established

- **(a) or (b) above.** The single measurement that would settle it: have the framework report
  whether it synchronises translated-block stores to the `Core` at a segment or service boundary, or
  expose the counter through a path that reads Lightrec's own memory. Until then the test is red and
  says why.
- **Whether the real card depends on (b).** If guest stores inside a translated block genuinely do
  not reach guest RAM mid-block, that is a far larger finding than this test and it would explain
  `0x800A069F` never clearing. **This issue does not claim that** — it names it as the next question.

## Falsifier

1. `tekken3_mode_call_budget_resume` going green with the body unchanged. Today: red, with
   `$t3 == 0` after 24,696 instructions per field.
2. A framework statement that guest stores are synchronised to the `Core` at every segment boundary,
   which would make this the *second* option and refute the first. Nothing in the tree says either.
3. `docs/issues/0020`'s census selftest failing. Today: pins found, negatives absent.
