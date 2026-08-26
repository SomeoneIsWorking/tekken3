---
id: I010
kind: instrument
status: trusted
created: 2026-08-26
---

## Instrument

Tekken controlled Getstat response interpreter/recompiler boundary

## Validated by

On hashed SLUS_004.02, tools/cd_response_boundary.py verifies 2/2 generated artifacts before tests/cd_response_boundary.cpp runs 668 shipping-emitted instructions and the executable interpreter from the same INT3 controller state. They agree 34/34 CPU, 38/38 unique RAM bytes, and 4/4 CDC fields; response 0x02 publishes and advances init 0x16->0x17, while the 0x00 negative control retains status/motor-off and step 0x16 in both engines.

## Known failure modes

(none recorded yet)
