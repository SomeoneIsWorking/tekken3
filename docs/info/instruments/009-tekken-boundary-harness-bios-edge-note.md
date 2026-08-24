---
id: I009
kind: instrument
status: trusted
created: 2026-08-24
tags: t3-04,oracle,bios,harness
depends: tools/bios_edge.py#validate_bios_edge, tools/recomp_boundary.py#verify_external_call, tests/recomp_boundary.cpp#tekken3_boundary_note
reconfirmed: 2026-08-24
verified_at: 2026-08-24
---

## Instrument

The boundary harness's BIOS-edge leg: `tests/recomp_boundary.cpp` reports the generated CPU's
actual t2/t1 kernel-vector dispatch registers (`# RECOMP-BIOS vector=... function=...`) after the
measured wrapper returns. `tools/bios_edge.py` owns the marker grammar and exact pc/ra/t2/t1
contract; `tools/recomp_boundary.py` owns process capture. The validator refuses when the note is
absent, duplicated, or disagrees with the manifest.

## Shown-the-other-answer evidence

SELFTEST 11/11 feeds it a positive fixture (vector 0xB0 / function 0x19 parses), plus missing,
duplicate, wrong-vector, wrong-function, and wrong-return-register fixtures that refuse, alongside the pre-existing altered-source, short-trace,
wrong-hardware-register, unmeasured-boundary, and forced-a0 refusals. Live negative observed before
the fix landed: the first wiring (note in the generated dispatch default) printed NO note because
rec_dispatch routes vector 0xB0 straight to framework rec_dispatch_miss, never through the generated
switch — the refusal "generated runner emitted no BIOS-edge note" fired as designed. A second live
mis-read was caught by the manifest check itself: noting at stub ENTRY read stale t1=0x48 instead of
the dispatched 0x19.

Final post-hardening real-data run on SLUS_004.02 / psxport d2266f4b reported the values read from
the generated CPU (`t2=0xB0`, `t1=0x19`) exactly once at return `pc=ra=0x80085DEC`; its 11/11
selftest rejected all four marker classes plus a wrong return-register state.

## Limits

Certifies ONLY the single-engine generated leg at this edge. It cannot detect a wrong framework-HLE
model of B(0x19) beyond register shape, and it says nothing about independent-CPU agreement. That
requires both generic DPCR handling and an independently sourced B(19) model; issue #10 records the
exact intervening boundary.
