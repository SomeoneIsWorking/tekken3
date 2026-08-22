---
id: 7
title: Independent CPU oracle cannot resume after a modeled IRQ-register access
status: resolved
symptom: Tekken execution cannot be differentially compared past post-store PC 0x80085D98 even though independent IRQ semantics are known through 0x80085DA4
tags: framework,oracle,irq,blocker,t3-04
created: 2026-08-22
updated: 2026-08-22
---

## Evidence

The earlier `external/psxport/tools/oracle/oracle_shim.c` routed every non-RAM/scratch access to
`hw_access` and set `ORACLE_STOP_HARDWARE`. Tekken's selected executable touched I_MASK at
`0x80085D94`, so the CPU oracle ended at PC `0x80085D98`. The game-local isolated Mednafen IRQ target
proved the write/read/write transition through `0x80085DA4`, but could not advance the independently
executing CPU.

## Proper fix

Extend psxport's independent oracle bus with the narrow vendored Mednafen device owner, preserving the
same CPU/load-delay/timestamp pipeline. Keep every unsupported register as an explicit hardware stop and
add a hermetic positive sequence plus an unsupported-device opposite answer before consuming it here.
This is framework work and must not be duplicated game-side.

## Resolution

The framework oracle now routes only I_STAT/I_MASK through vendored Mednafen `irq.c`, preserving the
same CPU and its real load-delay/timestamp behavior. A 43/43 fixture proves write/read/write continuation;
the existing GPUSTAT case remains an unsupported-hardware stop, providing the opposite answer. Real
Tekken execution advances to `0x80085DB4`, where the oracle reports the next unsupported access:
WRITE32 of `0x33333333` to DPCR `0x1F8010F0` at instruction `0x80085DB0`.

## Current boundary

Tekken has 35/35 independent CPU agreement at five boundaries through the DPCR stop at `0x80085DB4`
and retains 3/3 independent IRQ-device agreement through `0x80085DA4`. It does not claim DPCR/DMA
semantics, CPU execution after that access, a frame, or gameplay.
