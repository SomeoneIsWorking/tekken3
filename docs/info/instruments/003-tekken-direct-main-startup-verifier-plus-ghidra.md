---
id: I003
kind: instrument
status: trusted
created: 2026-08-21
---

## Instrument

Tekken direct-main startup verifier plus Ghidra semantic witness

## Validated by

The shipping verifier accepted the modeled direct-main fixture and real selected executable, rejected wrong entry/main/next-call targets, delay words, initializer return, return guard, and loop back-edge, and refused framework libc-boundary vocabulary (10/10 fixtures, 18/18 real structural facts); Ghidra independently exposed the main target as an infinite game loop and the first initializer as a returning function.

## Known failure modes

(none recorded yet)
