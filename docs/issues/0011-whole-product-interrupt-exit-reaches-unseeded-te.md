---
id: 11
title: Whole-product interrupt exit reaches unseeded Tekken re-entry
status: investigating
symptom: tekken3_port aborts at recomp-MISS 0x80085DC4 after IRQ 0x004
tags: runtime,recompiler,interrupt,t3-04
created: 2026-08-25
updated: 2026-08-25
---

## Root cause


## What was tried / dead ends


## Resolution

## Operator findings 2026-08-25 (integration session)

Discriminated the failing `tekken3_recomp_boundary_selftest` while landing this tree:

- RED at psxport `8611d756` (this repo's pin) AND at `17981527` — the failure predates the
  integration session and is caused by the landed IRQ-resume work letting `oracle_trace` continue
  past the retired DPCR stop (`0x80085DB4` / `0x1F8010F0`), not by any unlanded file here.
  `scratch/build-irq-resume` (Aug 22) is the last known-green run.
- The oracle leg no longer stops at a hardware register at all: it consumes the full 120000-step
  cycle budget ("cycle budget consumed"), leaving mapped text at step 110630 into the exception
  vector (`pc=0x000000B0`) after the last JAL to `0x800862C8` (ra=`0x80085DEC`). A jump into the
  exception vector is an UNMODELED EXCEPTION in the oracle leg, not a new measured boundary —
  do not retarget `verify_hardware_stop` to it.
- The product-side counterpart stands: whole-program boot dispatches the retail entry and aborts
  at recomp-MISS `0x80085DC4` after IRQ `0x004`; the interrupt-context resume facts added to
  `titles/tekken3/executable.json` (`caller_base_load` .. `resume_branch_target`) are the RE data
  for the fix. `tekken3_interrupt_reentry_selftest` PASSES 1/1.
- Next step: teach the oracle shim (and the product substrate seeds) the context-save call at
  `0x80085DBC` / resume at `0x80085DC4`, then retire the stale hardware-stop assertion in
  `tools/recomp_boundary.py` against the MEASURED new stop — never against the exception vector.

## 2026-08-25 (second session) — VSync wedge root-caused and fixed; new frontier is the CD completion path

**Root cause of the post-resume freeze:** psxport raises no preemptive VBlank IRQs by design, and
every game must declare its sync primitives. Adapter runtimes do this through GameConfig::hle;
Tekken derives DIRECTLY (no GameConfig allowed), so nothing was installed — the guest's libetc
VSync ran as ordinary recompiled code, its counter never moved, and CdSync's deadline
(count + 0x3C0) could never arrive. The framework even announces this failure mode ("NONE
configured; the guest will spin in any real sync loop it reaches") but the direct-boot path never
called initBuiltins, so Tekken got no announcement either.

**Fixed (psxport 38a70a08 + this repo):**
- Framework: `GameRuntime::platformHlePlan()` — direct runtimes declare measured bindings +
  windows without the legacy bag; `initBuiltins()` consumes it; `Timing::vsyncHle` implements
  faithful VSync over EmulatedTime (query = fields elapsed; waits consume field intervals).
- This repo: `game/core/sync_native.{h,cpp}` binds libetc VSync at **0x800859A8**
  (Ghidra: FUN_800859a8 answers mode<0 by returning a vblank counter; sole caller family is CdSync
  FUN_80083b84 spinning it against deadline count+0x3C0, strings "CD ready"/"Sync:";
  body extent [0x800859A8,0x80085B20) from adjacent recompiler-discovered starts), declared via
  `Tekken3Runtime::platformHlePlan()`; `runPort` calls `initBuiltins()`.
- Verified: `[plat-hle] 1 hardware-sync primitive(s) installed`; boot advances past the old spin
  into CdSync/CDC territory; ZERO recomp-MISS lines; zero CD-timeout prints; runs indefinitely
  (>170 s unpaced) with no abort.

**New frontier (next):** boot rests inside the CdSync wait loop waiting for CD command completion.
With NO disc provisioned there is nothing to read; next step is a disc-provisioned bounded run to
separate "waiting on media" from "waiting on an unclaimed CDROM IRQ delivery path", then own that
delivery (the SysEnq chain is empty by design here — completions must ride the HookEntryInt custom
exit). The boundary selftest stays red until verify_hardware_stop is retargeted at the MEASURED new
stop under a provisioned run — never at the exception vector.
