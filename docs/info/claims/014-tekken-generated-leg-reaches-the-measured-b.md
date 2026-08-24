---
id: C014
kind: claim
status: holds
created: 2026-08-24
tags: t3-04,oracle,bios,dma,dpcr
depends: tools/bios_edge.py#validate_bios_edge, tools/recomp_boundary.py#verify_external_call, tests/recomp_boundary.cpp#tekken3_boundary_note, titles/tekken3/executable.json
reconfirmed: 2026-08-24
verified_at: 2026-08-24 20:05:28
---

## Claim

On the selected SLUS_004.02 image, shipping-emitted Tekken execution continues past the DPCR write
through `FUN_80086264` (1050-word clear), `FUN_800862D8` (callee-saved context save), and the A/B
stub `FUN_800862C8` (`li t2,0xB0`; delay `li t1,0x19`; `jr t2`) to the caller return
`ra=pc=0x80085DEC`, with kernel vector-0xB0 function 0x19 (HookEntryInt, public PSX kernel ABI)
modeled by framework HLE. This edge is SINGLE-ENGINE evidence: no independent-CPU agreement is
claimed there.

## Evidence

2026-08-24 on fbda8b68..., framework d2266f4b: the boundary gate's generated leg reached
0x80085DEC with ra=pc=0x80085DEC and actual generated CPU registers t2=0x000000B0 / t1=0x19,
reported by exactly one RECOMP-BIOS note; 35 CPU fields captured at that stop. The five independent
35/35 comparisons through the DPCR stop at 0x80085DB4, IRQ 3/3 + SELFTEST 2/2, and SELFTEST 11/11
(including missing-note, duplicate-note, wrong-vector, wrong-function, wrong-return-register,
unmeasured-boundary, wrong-hardware-register, altered-source, and forced-a0 refusals) passed in the
same run; cpp-policy format/size/tidy and smoke 8/8 green; pin bumped to d2266f4b after those gates.

## What would falsify it

Falsified if any tracked frontier word changes, the generated leg stops or refuses to reach
0x80085DEC or emits a second/different BIOS note, framework HLE changes B(0x19) semantics so the
captured state differs, or — decisively — when generic DPCR plus an independently sourced B(19)
model lets the independent CPU reach this edge with different registers.

## Re-confirmed 2026-08-24

Final post-hardening Clang gate on SLUS_004.02 / psxport d2266f4b: five independent/generated 35/35
comparisons through DPCR 0x80085DB4; IRQ 3/3 and SELFTEST 2/2; generated DPCR 0x33333333;
register-derived t2/t1 marker B0/19 returned to 0x80085DEC; SELFTEST 11/11 rejected missing,
duplicate, wrong-vector, wrong-function, wrong-return-register, altered-source,
wrong-hardware-register, unmeasured-boundary, and forced-a0 cases.

## Re-confirmed 2026-08-24

On pinned psxport bc8c8897, authoritative verify reconfirmed the register-derived B0/19 edge to pc=ra=0x80085DEC, while retaining the explicit single-engine/no-frame limitation; five independent 35/35 comparisons through DPCR, IRQ 3/3 + selftest 2/2, and boundary selftest 11/11 passed.

## Re-confirmed 2026-08-24

Post-landing authoritative verify reconfirmed the register-derived B0/19 generated-only edge to pc=ra=0x80085DEC and all BIOS-edge refusal controls
