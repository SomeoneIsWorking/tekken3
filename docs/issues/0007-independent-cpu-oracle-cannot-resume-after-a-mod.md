---
id: 7
title: Independent CPU oracle cannot resume after a modeled IRQ-register access
status: open
symptom: Tekken execution cannot be differentially compared past post-store PC 0x80085D98 even though independent IRQ semantics are known through 0x80085DA4
tags: framework,oracle,irq,blocker,t3-04
created: 2026-08-22
updated: 2026-08-22
---

## Evidence

`external/psxport/tools/oracle/oracle_shim.c` routes every non-RAM/scratch access to `hw_access`, sets `ORACLE_STOP_HARDWARE`, and has no API that supplies a device read/write result then resumes the same CPU pipeline. Tekken's selected executable touches I_MASK at `0x80085D94`; the CPU oracle ends at PC `0x80085D98`. The game-local isolated Mednafen IRQ target proves the write/read/write transition through `0x80085DA4`, but cannot advance the independently executing CPU.

## Proper fix

Extend psxport's oracle with a narrow modeled-I/O resume mechanism backed by Mednafen device semantics: expose the pending access width/direction/value, apply the actual IRQ controller result, preserve the same CPU/load-delay/timestamp pipeline, and resume. Add a hermetic positive sequence plus wrong-readback/refusal cases in psxport before using it here. This is framework work and must not be duplicated game-side.

## Current boundary

Tekken retains 35/35 independent CPU agreement through post-store `0x80085D98` and 3/3 independent IRQ-device agreement through `0x80085DA4`. It does not claim CPU agreement after hardware, a frame, or gameplay.
