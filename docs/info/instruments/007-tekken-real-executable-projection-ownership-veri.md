---
id: I007
kind: instrument
status: trusted
created: 2026-08-22
---

## Instrument

Tekken real-executable projection ownership verifier

## Validated by

On hashed SLUS_004.02, tools/verify_projection.py passes 33/33 measured facts and 7/7 tests. It was forced to the other answer by a reserved-bit mutation of a real CTC2 writer, canonicalizing the resident data word 0x48CCCCCE, changing a preset width, changing a stage clip bound, and redirecting a projection JAL; missing projection metadata is refused.

## Known failure modes

(none recorded yet)
