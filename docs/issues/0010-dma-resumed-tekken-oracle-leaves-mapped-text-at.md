---
id: 10
title: DMA-resumed Tekken oracle leaves mapped text at B0
status: investigating
symptom: after modeling DPCR the independent CPU cannot reach the BIOS-call return and later reports a nonsensical hardware address
tags: framework,oracle,bios,dpcr,t3-04
created: 2026-08-24
updated: 2026-08-24
---

## Root cause

The independent `oracle_trace` maps only the selected executable, not a PSX BIOS or a semantic BIOS
call boundary. Once experimental generic DPCR handling lets the same CPU execute beyond
`0x80085DB4`, the measured wrapper `FUN_800862C8` loads `t2=0xB0`, loads `t1=0x19` in the jump
delay slot, and leaves mapped title text at step 110630 with `pc=0x000000B0` and
`ra=0x80085DEC`. The generated leg returns only because psxport HLE models B(19) HookEntryInt;
that is not an independent implementation.

## What was tried / dead ends

`scratch/raw/t3-04/oracle-dpcr-next.trace` was allowed to continue after leaving mapped text. It
eventually stopped on address `0xFFFF8C94`, but the trace itself records that everything after
step 110630 is not game code from the image. Treating `0xFFFF8C94` as the next hardware boundary,
or treating DMA support alone as sufficient to compare at `0x80085DEC`, is invalid.

## Resolution

Still open. The next exact independent boundary is the BIOS ABI edge B(19), not another hardware
register. Add a generic, independently sourced B-vector model (or execute a mapped BIOS) after
generic DPCR support, prove B(19) with positive and unsupported-function controls, then compare the
same independent CPU with the generated leg at caller return `0x80085DEC`. Only that resumed CPU
may identify the next real hardware boundary.
