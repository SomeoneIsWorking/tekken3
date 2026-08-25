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

## 2026-08-25 (third pass, same session) — provisioned-run evidence for the CD frontier

With the disc provisioned (`.env`, gitignored) and the VSync HLE live:

- Tekken's CDC traffic reaches the framework: `[cdc] cmd 0x01` (Getstat) spam plus 0x0A/0x0C during
  init; the CDC machine answers each with an INT3 response and raises its edge
  (19 × "CD raised IRQ2" in 30 s with `PSXPORT_DEBUG=irq`).
- **The guest runs libcd in POLLED mode**: it writes `I_MASK = 0` (ra=0x80085BE8, right past the
  VSync body), so `pending = I_STAT & I_MASK` stays 0 and the HookEntryInt custom exit fires exactly
  once across the whole run. Completions latch into I_STAT but nothing delivers while masked —
  which may be CORRECT retail behaviour for this phase; the guest is supposed to observe
  completions through its own MMIO poll instead.
- That MMIO poll is the next suspect: CdSync's drain routine (FUN_800833A8) reads the CD interrupt
  flag register through `*DAT_80099a24`; our `cdc_read` reg 3 returns `0xE0 | type` whenever a
  response is queued, which LOOKS right — so the open question is whether Tekken's reads reach
  `cdc_read` at all (bank/index handling around 0x1F801800-0x803) or whether the response is
  consumed by an earlier ack. Instrument `cdc_read`'s callers before touching semantics.
- Nondeterministic abort (~12 s in, SIGABRT family) observed ONLY with heavy debug logging on
  (`PSXPORT_DEBUG=vsync` floods ~500k lines); the diagnostic is lost to stdio buffering on abort.
  Reproduce with `PSXPORT_LOG_FILE` set before chasing it. Not observed without the flood.

## 2026-08-25 (fourth pass) — the polled CD path WORKS; the residual wedge is host throughput

Subagent infrastructure was down (provider endpoint failures), so this pass ran solo. Findings,
each measured on live runs:

- **The MMIO poll reaches our CDC model and observes completions.** `PSXPORT_DEBUG=cdcr` shows
  FUN_800833A8 (libcd's drain) reading reg 3 (`0xE3`/`0xE2` INT types), consuming the response FIFO
  byte, and acking back to `0xE0`, cycling forever — the earlier hypothesis "the poll never sees
  INT flags" is FALSIFIED.
- **Tekken's HookEntryInt handler (FUN_80085E34) also runs repeatedly**, not once: it drains via
  FUN_80084A30 (ra=0x80085F10 inside the handler body), walks its 11-bit event table, and carries
  an "intr_timeout" counter of its own. The single custom-exit TRACE line was an artifact of where
  tracing sits, not of delivery count.
- **The actual wedge is throughput**: six staggered SIGINT samples spread across CdSync
  (0x80083B84+0x671), its caller 0x80091328, cdc_drive_service and plain mem_w32 — no hot spin, a
  grind. perf over 12 s at 99 Hz (1231 samples):
  - `Core::mem_w32` 20.7 % + `OtAttr::trackStoreSlow` 16.4 % — **~37 % of host time is the
    per-guest-store attribution diagnostic**
  - `cdc_drive_service` 14.1 % · `rec_guest_instruction_ticks` 11.8 % · `mem_r32` 6.0 %
    · `Timing::vsyncHle` 4.75 % · `gen_func_80083B84` 4.25 % · `__udivti3` 4.2 %
    (the 128-bit divide inside `EmulatedTime::hSyncCount`, paid per VSync query)
- A clean 7-minute run (no channels) produced ZERO new log lines past CD_init: at ~0.6 CD commands/s
  the retail init cannot reach a first present in practical time. This mirrors why Tomba ported its
  vblank busy-waits natively rather than executing them.

**Ranked next steps:**
1. Make the per-store attribution path pay rent only when it can record anything: `trackStoreSlow`
   should be unreachable (inlined/early-out at the mem_w32 call site) when the game's packet pool is
   unconfigured — Tekken's is 0 — without weakening it where the pool exists. Hermetic test first.
2. Give `EmulatedTime::hSyncCount` a Q32-shift/divide-free fast path (multiply by a precomputed
   reciprocal) or cache fields-per-tick; `__udivti3` at 4 % is pure waste.
3. After those, re-measure commands/s; if still impractical, own Tekken's CD wait primitive natively
   (the Tomba playbook: sync_native.cpp gains the leaf, RE-proven).
4. ONLY THEN retarget `verify_hardware_stop` against the measured stop under a provisioned run.
