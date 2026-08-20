---
id: C002
kind: claim
status: holds
created: 2026-08-21
tags: provisioning,t3-02
depends: tools/provision_executable.py#run
reconfirmed: 2026-08-21
verified_at: 2026-08-21 02:47:16
---

## Claim

Tekken 3 executable provisioning deterministically resolves the operator input and refuses unless the extracted USA SLUS_004.02 matches all eight tracked identity/header facts.

## Evidence

tools/provision_executable.py passed 12/12 shipping-path precedence, match, byte mismatch, malformed-executable mismatch, preservation, ambiguity, and refusal fixtures; a real CHD extraction produced 1,185,792 bytes, SHA-256 fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c, entry 0x80079C70, and text extent [0x80010000,0x80131000).

## What would falsify it

A supported resolution source selects a lower-priority disc, a bad configured path falls through, a mismatch remains usable, or a fresh selected-USA extraction changes any tracked identity/header fact.

## Re-confirmed 2026-08-21

Post-landing tool selftest passed 12/12 including malformed PS-X EXE mismatch; the real USA extraction remains bound to the recorded 8/8 identity/header facts.
