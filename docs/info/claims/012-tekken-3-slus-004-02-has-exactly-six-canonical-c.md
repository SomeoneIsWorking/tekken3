---
id: C012
kind: claim
status: holds
created: 2026-08-22
tags: rendering,widescreen,reverse-engineering
depends: tools/verify_projection.py#verify_projection, titles/tekken3/executable.json#projection, psxport.pin
reconfirmed: 2026-08-22
verified_at: 2026-08-22 19:13:26
---

## Claim

Tekken 3 SLUS_004.02 has exactly six canonical CR24/CR25/CR26 writers; its boot display/view preset is 368x448 versus a distinct 384x480 projection, H initializes to 500, the stage selector receives authored 600/780 wedges, and retail right clipping has eleven stage plus one effect rendering sites distinct from one 2D text-slide use.

## Evidence

The shared-decoder-backed real-executable verifier passes 33/33 measured facts and 7/7 positive, mutated-disagreement, and refusal cases. Ghidra independently identifies the six instruction owners and the display, projection, camera, stage selector, stage clip, effect clip, and 2D text owners. Full Clang verify and CTest 6/6 pass against psxport 57a17a14.

## What would falsify it

Falsified if the selected executable identity changes; the complete canonical decoder census gains or loses a CR24/25/26 writer; raw preset/call/clip bytes change; Ghidra assigns different code ownership; or the real verifier cannot detect its reserved-bit, preset, call-target, and clip-bound mutations.

## Re-confirmed 2026-08-22

2026-08-22 shared-decoder-backed real-executable projection gate passed 33/33 facts and 7/7 positive, mutated-disagreement, and refusal cases against recorded psxport 57a17a14; full Clang verify and CTest 6/6 passed.

## Re-confirmed 2026-08-22

Post-commit 1022430 shared-decoder-backed real-executable projection gate passes 33/33 facts and 7/7 positive, disagreement, and refusal cases; full Clang verify and CTest 6/6 pass against psxport 57a17a14.
