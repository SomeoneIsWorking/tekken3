---
id: 6
title: I_MASK frontier was labeled before the access after the store already ran
status: resolved
symptom: Tekken docs and C007 call 0x80085D98 pre-I_MASK even though the oracle stops on the SH at 0x80085D94
tags: harness,reverse-engineering,irq,evidence
created: 2026-08-22
updated: 2026-08-22
---

## Evidence

The selected executable has `A4400000` (`sh zero,0(v0)`) at `0x80085D94`; the independent oracle reports hardware address `0x1F801074` and ends with PC `0x80085D98`. The generated slice also executes the store before its `0x80085D98` hook.

## Root cause

The prior report treated the captured next PC as the address of the unexecuted hardware instruction. The oracle memory callback actually stops during the store and the CPU retires to its successor address.

## Resolution

Falsify C007's pre-access wording. Track the exact four-word reset sequence from the executable, retain
the 35/35 CPU comparison at the honest post-store boundary, and compare the emitted write/read/write
device effects with the separately compiled vendored Mednafen IRQ controller through `0x80085DA4`.
The shared oracle now continues that sequence on the same CPU; the remaining blocker is the following
unsupported DPCR access, not the first I_MASK store itself.
