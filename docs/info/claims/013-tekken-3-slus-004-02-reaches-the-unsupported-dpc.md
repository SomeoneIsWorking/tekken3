---
id: C013
kind: claim
status: holds
created: 2026-08-22
tags: t3-04,oracle,dma,dpcr
depends: tools/recomp_boundary.py#compare_boundary, tests/recomp_boundary.cpp#main, titles/tekken3/executable.json
reconfirmed: 2026-08-22
verified_at: 2026-08-22 19:41:47
---

## Claim

Tekken 3 SLUS_004.02 reaches the unsupported DPCR write boundary at 0x80085DB4 on one independent Mednafen CPU and agrees with shipping-emitted execution on all 35 CPU fields.

## Evidence

On fbda8b68..., the verifier checked the five hardware-frontier instruction words, kept the same independent CPU through I_MASK/I_STAT, and compared 35/35 fields at five boundaries including oracle step 106395 / PC 0x80085DB4. The oracle stopped on DPCR 0x1F8010F0; the generated path stored a1=0x33333333 there. Boundary SELFTEST 9/9, IRQ SELFTEST 2/2, Clang policy, CTest 6/6, and framework oracle 43/43 / CTest 85/85 passed.

## What would falsify it

Falsified if the selected executable or tracked frontier words change, the same-CPU oracle no longer reaches 0x80085DB4 at DPCR 0x1F8010F0, any of the 35 CPU fields differ there, or generated execution does not store 0x33333333.

## Re-confirmed 2026-08-22

Final Clang-backed gate on the complete dirty integration: five-boundary 35/35 comparison through 0x80085DB4; DPCR 0x1F8010F0 stop and generated 0x33333333 store; boundary SELFTEST 9/9, IRQ SELFTEST 2/2, CTest 6/6, and cpp-policy format 7/7, size 7/7, clang-tidy 6/6. Framework oracle 43/43 and CTest 85/85.

## Re-confirmed 2026-08-22

Authoritative verify target passed on the complete integration against recorded framework base 57a17a14: exact SLUS_004.02 boundary 35/35 through DPCR stop 0x80085DB4, generated DPCR 0x33333333, IRQ 3/3 plus SELFTEST 2/2, boundary SELFTEST 9/9, boot oracle 3/3, runtime seam/contract, projection 7/7, Clang format/size and tidy 6/6, framework smoke 8/8.

## Re-confirmed 2026-08-22

Post-framework-cleanup authoritative verify remained green: 35/35 at all five real boundaries through DPCR stop 0x80085DB4; generated DPCR=0x33333333; IRQ 3/3, IRQ SELFTEST 2/2, boundary SELFTEST 9/9, Clang policy, projection 7/7, runtime contract/seam, boot oracle 3/3, pin check, and smoke 8/8.

## Re-confirmed 2026-08-22

Post-change authoritative verify remained green: serial identity, five-boundary 35/35 oracle/generated comparison through DPCR, IRQ controls, projection 7/7, Clang format/size/tidy, runtime seam, pin and smoke gates passed on 2026-08-22.
