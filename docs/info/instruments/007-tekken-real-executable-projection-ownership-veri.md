---
id: I007
kind: instrument
status: trusted
created: 2026-08-22
---

## Instrument

Tekken real-executable projection ownership verifier

## Validated by

On hashed SLUS_004.02, tools/verify_projection.py passes 38/38 measured facts and 8/8 tests. It was forced to the other answer by a reserved-bit mutation of a real CTC2 writer, canonicalizing the resident data word 0x48CCCCCE, changing a preset width, changing a stage clip bound, redirecting a projection JAL, and redirecting the post-CD projection-owner edge; missing projection metadata is refused.

## Known failure modes

(none recorded yet)
