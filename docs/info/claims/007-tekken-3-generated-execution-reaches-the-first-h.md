---
id: C007
kind: claim
status: holds
created: 2026-08-22
tags:
depends: tools/recomp_boundary.py#compare_boundary, tests/recomp_boundary.cpp#main, titles/tekken3/executable.json
---

## Claim

Tekken 3 generated execution reaches the first hardware boundary before the I_MASK write and agrees with independent Mednafen on all 35 CPU fields.

## Evidence

On the provisioned USA executable fbda8b68..., the Clang-built shipping-emitter runner and Mednafen oracle agreed 35/35 at 0x80085D98 (oracle step 106388), after the measured indirect 0x80085BC8 -> 0x80085D5C dispatch. The oracle ended there because the next instruction accesses I_MASK 0x1F801074. tools/recomp_boundary.py SELFTEST 7/7 proved opposite answers for a register mismatch, altered generated source, absent edge, wrong hardware register, and unmeasured target.

## What would falsify it

Falsified if the real executable changes, the emitted slice source changes without a renewed compare, the measured indirect target differs, the oracle no longer stops at 0x80085D98/0x1F801074, or any of the 35 CPU fields differs there.
