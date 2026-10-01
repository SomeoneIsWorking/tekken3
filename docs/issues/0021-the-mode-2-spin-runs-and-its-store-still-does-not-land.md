---
id: 21
title: Six errors in a hand-assembled guest body, and the framework exonerated
status: resolved
symptom: a synthetic spinning mode body executed ~25k instructions per field and the counter it wrote every iteration stayed 0
tags: tekken3,test-fixture,hand-assembly
created: 2026-09-29
updated: 2026-09-29
---

**Dead end, kept for the rule it produced.** The symptom was first read as a possible framework
synchronisation defect — Lightrec holding translated-block stores somewhere and syncing them at a
segment boundary, which would have borne directly on the real card's `0x8006C2EC` store. That was
wrong: there is no second RAM buffer, and the real cause was the fixture. Six errors in a 16-word
hand-assembled MIPS body, five of which produced a *plausible* mnemonic, and only the sixth explains
the symptom — the body consumed a `lw` result on the very next instruction, which an R3000 does not
allow. A `nop` after a load is not decoration.

The rest of the errors are the same lesson from the other side: a branch offset is the 16-bit field
sign-extended from PC+4 (`0xFFFF` is -1, not -7); `beq $zero,$zero` is an unconditional branch that
Capstone prints as `b`; a J-type target is `target >> 2` and absolute, not PC-relative; and a
register field can be wrong while the mnemonic still reads correctly. **Compare instruction FIELDS,
never the rendered mnemonic.**

The frame-loop change the test justifies is correct and kept: mode 2 legitimately outlives a display
field, so every mode body dispatches through `BoundedCall` rather than the non-suspending entry.