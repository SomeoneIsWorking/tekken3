---
id: 7
title: The independent CPU oracle stopped at the first modeled IRQ-register access
status: resolved
symptom: Tekken execution cannot be differentially compared past post-store PC 0x80085D98 even though independent IRQ semantics are known through 0x80085DA4
tags: framework,oracle,irq
created: 2026-08-22
updated: 2026-08-22
---

**Dead end:** routing every non-RAM access to `hw_access` and stopping means the independent CPU dies
at the first device register the executable touches — `I_MASK` at `0x80085D94`. Proving the device's
semantics in a separate target does not advance the independently executing CPU; the bus itself has to
model it.

Resolved in the framework: only `I_STAT`/`I_MASK` now route through vendored Mednafen `irq.c`,
preserving the same CPU and its real load-delay behaviour, with every other register still an explicit
hardware stop as the opposite answer. Tekken then reaches its first unsupported access,
`WRITE32 0x33333333` to DPCR `0x1F8010F0` at `0x80085DB0`, which issue 0010 carries forward.