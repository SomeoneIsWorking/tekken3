---
id: C010
kind: claim
status: holds
created: 2026-08-22
tags: t3-04,irq,oracle
depends: tools/recomp_boundary.py#verify_interrupt_reset, tests/recomp_boundary.cpp#main, tests/irq_oracle.cpp#main, titles/tekken3/executable.json
reconfirmed: 2026-08-22
verified_at: 2026-08-22 19:08:19
---

## Claim

Tekken 3 shipping-emitted execution reaches the completed interrupt-controller reset at 0x80085DA4 with device semantics matching independent Mednafen.

## Evidence

On the provisioned USA SLUS_004.02 fbda8b68..., the verifier checked the exact 0x80085D94..0x80085DA0 instruction words against the executable. Independent Mednafen CPU and the generated path agreed 35/35 on the post-store CPU boundary at 0x80085D98. A separate process compiling vendored Mednafen irq.c showed both non-zero and reset states (SELFTEST 2/2), then agreed with the generated path on I_MASK readback, final I_STAT, and final I_MASK (3/3) at 0x80085DA4. The complete harness passed SELFTEST 9/9 and CTest 4/4.

## What would falsify it

Falsified if the selected executable or tracked reset words change, the CPU comparison differs at 0x80085D98, Mednafen IRQ and psxport differ on any of the 3 device observations at 0x80085DA4, or the opposite-answer IRQ fixture can no longer produce a non-zero state.

## Re-confirmed 2026-08-22

Re-verified after final code/docs edits: CTest 4/4; exact SLUS_004.02 instruction words; 35/35 CPU fields at post-store 0x80085D98; 3/3 Mednafen IRQ device observations at 0x80085DA4; boundary SELFTEST 9/9 and IRQ SELFTEST 2/2; Clang policy 6/6 format/size and 5/5 tidy.

## Re-confirmed 2026-08-22

2026-08-22 final gate after framework pin ad5cf802: exact reset words passed; CPU 35/35 at post-store 0x80085D98; isolated Mednafen IRQ 3/3 at 0x80085DA4 with IRQ SELFTEST 2/2; boundary SELFTEST 9/9; Clang format/structure 7/7 and tidy 6/6; CTest 5/5.

## Re-confirmed 2026-08-22

2026-08-22 full Clang verify passed 35/35 CPU agreement through 0x80085D98, 3/3 independent Mednafen IRQ observations through 0x80085DA4, IRQ oracle SELFTEST 2/2, and boundary SELFTEST 9/9.
