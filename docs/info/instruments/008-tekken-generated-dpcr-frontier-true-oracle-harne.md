---
id: I008
kind: instrument
status: trusted
created: 2026-08-22
---

## Instrument

Tekken generated DPCR-frontier true-oracle harness

## Validated by

Produced both required answers on real SLUS_004.02: same-CPU oracle/generated agreement 35/35 at 0x80085DB4 after the modeled IRQ block, then an explicit unsupported-hardware stop on DPCR 0x1F8010F0. The production comparator rejects an altered a0; integrity/refusal gates reject changed source, missing edge, wrong hardware register, and unmeasured boundary (SELFTEST 9/9). Framework oracle independently proves modeled IRQ continuation and unsupported GPUSTAT stop (43/43).

## Known failure modes

(none recorded yet)
