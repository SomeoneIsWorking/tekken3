---
id: 11
title: Whole-product interrupt exit reaches unseeded Tekken re-entry
status: investigating
symptom: tekken3_port aborts at recomp-MISS 0x80085DC4 after IRQ 0x004
state_items: S004,S008
tags: runtime,recompiler,interrupt,t3-04
created: 2026-08-25
updated: 2026-08-31
---

## Root cause

The current whole-product wedge is libcd queue-kick starvation while the CD-system state is not
ready state `1`. It is not upstream of the first read request: the saved
provisioned discriminator's watchdog stack is inside
`FUN_80091858 -> FUN_80091E5C -> FUN_80091328`, after `FUN_80090F78` has accepted the four-command
`Pause -> Setmode -> Setloc -> ReadN` group and entered its sector-count wait.

`FUN_8008F08C` allocates all four queue entries and returns a nonzero group ID, but calls queue
executor `FUN_8008E8B8` only when `DAT_8009B750 == 1`. The same run issued only Getstat (`0x01`)
after CdInit's Reset/Demute traffic and never issued a queued command. This excludes state `1`, but
does **not** discriminate initializing state `2` from failed state `3`; the earlier state-3 inference
was too strong.

The saved trace proves more of the response path than the earlier write-up credited: each Getstat
reaches `FUN_800833A8` as INT3, reads response FIFO byte `0x02`, and acknowledges it. A new controlled
interpreter-versus-shipping-recompiler test proves the normal guest path copies that byte through
`DAT_800A3BD8`, invokes `FUN_80090128/FUN_800907D0`, publishes `DAT_8009B748=0x02`, and advances
init step `0x16 -> 0x17`. The remaining root cause is therefore a **live IRQ-context discriminator**:
the current command, route-table value, callback pointer/class, or CD state differs from that normal
path. It is not a static mistranslation of the six measured response functions.


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

## 2026-08-25 (fifth pass) — two hypotheses tested and one falsified; the ba2 lead

- **Census-tax lever DEAD.** Live A/B by flipping `g_producer_census_armed` inside the running
  process (`gdb -p PID -batch -ex 'set variable g_producer_census_armed=false'`): 13.1 → 12.9
  fields/s (×0.99). The 37 % profile share is the price of the workload's own store volume, not a
  removable drag. NOTE the related latent defect this exposed: the arm is assigned in
  native_boot.cpp:883, which direct-boot runtimes NEVER run — so PSXPORT_PRODUCERS silently does
  nothing on tekken3 today. Wherever that assignment lands long-term, it must be on a path every
  loop executes.
- **Sharper lead for why CdSync never concludes**: its drain is gated on FUN_80085D1C() ==
  *DAT_80099ba2, but the cdcr traces show every FUN_800833A8 invocation arriving from the HookEntryInt
  handler (FUN_80084A30 called at ra=0x80085F10 INSIDE FUN_80085E34) — and FUN_80085E34 sets ba2=1
  at entry and clears it before returning. If nothing else writes ba2, CdSync's gate reads it only
  BETWEEN handler runs, i.e. always 0, so the inner drain-and-flag-read never executes from CdSync's
  own context and the loop can end only via the 960-field deadline (~74 s at today's 13 fields/s).
  Next RE question: on retail, what writes ba2 outside the handler window (an INT3-hooked callback?
  the BIOS dispatcher prologue?), i.e. what makes the gate observable to the interrupted stream.
  Ghidra xref on 0x80099BA2 stores is the first command.

## 2026-08-25 (sixth pass) — oracle comparison kills the INT2 theory; the open question sharpened

- **Beetle ground truth**: Nop/Getstat (`Commands[0x01]`) has `func2 = NULL` — on the vendored
  oracle a Getstat produces a SINGLE INT3 ack and no completion interrupt (cdc.c:2227, :304).
  So "our CDC never queues INT2 for zero-delay commands" is CORRECT behaviour, not the bug; the
  sixth-pass INT2 theory is withdrawn.
- **CdSync structure** (full decompile, scratch/decomp/t3-cdsync-full.c): blocking only when
  `param_1 == 0`; completes via `DAT_80099a32` (INT2/case 4) OR `DAT_80099a31` (set by drain cases
  1/4/5 — data-ready/error — but NEVER by case 3, the pure ack). A Getstat-only command therefore
  cannot complete through this function on ANY implementation — so retail must either call it
  non-blocking (`param_1 != 0`, returns 0 immediately) from a caller that tracks completion
  elsewhere, or the responses Tekken waits on carry types 1/2/4/5, not bare acks.
- **Sample histogram** (10 single-SIGINT runs, 6–33 s): gen_func_80083B84 ×3 at host offsets
  +0x10/+0x671/+0x879 (host offsets do not map to source branches), plus prior samples in its
  caller 0x80091328. Consistent with heavy churn through CD sync paths, not one tight spin.
- **New tool**: tools/ghidra_query.py (adapted from spider1's; project tekken3_boot, program
  /ram_boot.bin) — `python3 tools/ghidra_query.py xrefs <addr>` gives real data xrefs. It proved
  0x80099BA2 has exactly 3 references (read FUN_80085D1C; write×2 FUN_80085E34), closing the ba2
  question: nothing else writes the gate.

**Sharpened open question for the next session:** map Tekken's libcd callback registration
(DAT_80099754/DAT_80099750 writers — Ghidra xref both) and enumerate callers of 0x80083B84 with
their `param_1` argument (Ghidra xref + decompile each caller). Decide from THAT whether the wedge
is (a) a caller polling non-blocking forever because a flag the HANDLER should set lands in the
wrong buffer, or (b) genuinely blocking waits whose responses carry unexpected types. Do not
modify CDC semantics until that decision is written down — beetle agrees with our current model.

## 2026-08-25 (seventh pass, delegated + operator discriminator run) — command trace narrowed the read-path wedge

Full evidence: scratch/t3-11-seventh-pass-notes.md (READ-ONLY agent session; decompiles
scratch/decomp/t3-11-*.c). The response-path evidence below survived, but the call-site census did
not: the complete Ghidra xref query run on 2026-08-27 reports five direct calls to `0x80083904`
(`0x80082D64`, `0x80083138`, `0x80083F0C`, `0x8008469C`, and `0x8008FC34`), and the live boot chain
enters it from `FUN_80083E4C` with blocking mode `0`. The earlier two-caller/nonblocking-only premise
must not be used to choose the mechanism.

- (a) dead: handler-side and poller-side drains feed identical slots; completion chain
  drain cases 1/4/5 → slot 0x80099754 (FUN_8009073C) → DAT_800A3EE0 = FUN_8008F850 → done-flags
  DAT_800A3D68/58 — statically coherent end-to-end. Callback registrations installed by
  FUN_8008F958 (slot750=FUN_80090128 ack-class, slot754=FUN_8009073C completion-class,
  vblank event 0 = FUN_8008FDE8 — the retail IDLE GETSTAT TICKER, which explains the cmd-0x01
  spam as normal behaviour).
- Beetle oracle cross-check: ReadN/Setloc/Setmode/Nop/Demute are single-INT3 (func2=NULL);
  read DATA rides INT1-per-sector — nothing in our CDC needs changing for those.

**Operator discriminator run** (provisioned, `PSXPORT_DEBUG=cdc,cdcr`, 90 s): command histogram
49× 0x01, 1× 0x0A, 1× 0x0C — and irq flags ONLY E0/E3/E2 (acks + the two-phase completions of
0x0A/0x0C). Per the seventh-pass decision table this is the third locus: **the read group
{Pause, Setmode, Setloc, ReadN} built by FUN_80090F78 is never queued at all** — no 0x06/0x09/0x02/
0x0E ever issues. The wedge is therefore UPSTREAM of libcd's read machinery: whatever gates the
FIRST sync-op (the caller chain feeding FUN_80090F78/FUN_80091E5C, pumped by game-main
FUN_8006AB64 case 3) never fires within 90 s emulated.

**Next implementation step:** Ghidra-xref FUN_80090F78's callers; for each, evaluate its enable
condition against LIVE RAM during a provisioned run (WWATCH or gated diagnostics on the exact flag
address). Suspect ordering: another earlier wait/starvation in Tekken's pre-read init — the
vblank-ticker running (FUN_8008FDE8 alive) proves CD-system init completed, so the gate is above
the CD subsystem, not inside it.

## 2026-08-26 (eighth pass) — saved runtime stack falsifies the upstream-call gate; queue state is the wedge

The seventh-pass command histogram proved that no read-group command reached the CDC, but not that
Tekken never requested the group. Its saved runtime log contains the missing opposite-side
observation:

- `scratch/logs/tekken3-discriminate.log` ends inside
  `gen_func_80091328 <- gen_func_80091E5C <- gen_func_80091858 <- gen_func_80091558`.
  `FUN_80091E5C` calls `FUN_80090F78` once before entering that wait, so the read request was reached
  and accepted. This **falsifies** the seventh-pass conclusion that the wedge is upstream of the
  first sync operation.
- Ghidra's complete xref census gives one caller of `FUN_80090F78` (`FUN_80091E5C`), three calls to
  `FUN_80091E5C` (two in `FUN_80091858`, one in `FUN_80091BC0`), and both higher-level functions are
  only called by `FUN_80091558`. The observed stack is the real directory-read path.
- `FUN_8008F08C` queues four entries, increments `DAT_800A3E40` four times, and returns the group ID
  whether or not it kicks the head. The sole immediate-kick condition is
  `FUN_8008FBB4(0) == 1`, or `DAT_8009B750 == 1`; no later callback retries the kick.
- Persistent post-enqueue Getstat excludes ready state `1`. It does not by itself distinguish state
  `2` from state `3`; the ninth pass below corrects that inference.

This pass changes no CDC semantics. The next serialized provisioned run must watch
`[0x8009B734,0x8009B780)` and capture current command, published status, callback class, and the
state `2`/`3` discriminator in one range. The proper fix belongs at the first live value that differs
from the differential-green path. Forcing state `1`, explicitly kicking the queued head, or
accepting state `3` would only bypass the broken invariant.

Run it only when no other game instance is active. `timeout` owns and signals only the child it
starts; it never matches the shared executable name:

```sh
timeout --signal=INT --kill-after=5s 40s \
  env PSXPORT_NOPACE=1 PSXPORT_NOAUDIO=1 PSXPORT_DEBUG=cdc,cdcr \
      PSXPORT_WWATCH=8009B734,8009B780 \
      PSXPORT_LOG_FILE=scratch/logs/t3-state-watch.log \
  ./scratch/bin/tekken3_port scratch/bin/tekken3/SLUS_004.02
```

The high watch address is exclusive, so `0x8009B780` includes the complete state word at
`0x8009B77C`. This run must first record whether the live path is state `2` or `3`, plus
`DAT_8009B734` (current command), `DAT_8009B748` (published status), and `DAT_8009B74C` (callback
class). If status receives a different value, the next bounded run watches the ack buffer
`PSXPORT_WWATCH=800A3BD8,800A3BE0`; if it is never written, the fault is earlier in
`FUN_800833A8`, and if it holds `0x02`, the fault is the callback argument/publication path.

## 2026-08-26 (ninth pass) — normal Getstat publication is differential-green; live IRQ context remains

`tools/cd_response_boundary.py` now emits 668 instructions from the six measured executable
functions using psxport's shipping emitter and verifies 2/2 generated artifacts before execution.
`tests/cd_response_boundary.cpp` seeds the same one-byte
INT3/Getstat controller response seen in the saved trace and runs `FUN_80084A30` once in the
interpreter and once in emitted C. The two engines agree 34/34 CPU values, 38/38 unique RAM bytes,
and 4/4 CDC queue fields. Both copy `0x02` to `DAT_800A3BD8`, publish
`DAT_8009B748=0x02`, set the motor-on flag, and advance init step `0x16 -> 0x17`.
The `0x00` negative control produces the other answer in both engines: published status and motor
flag remain zero and init step remains `0x16`.

This falsifies a normal-path translation defect in
`FUN_80084A30/FUN_800833A8/FUN_80090128/FUN_800903C8/FUN_800907D0/FUN_8009095C`. It also corrects
the eighth pass: state `3` was inferred, not observed, and state `2` also prevents the enqueue-time
kick. The proper next observation is the existing bounded state watch above. Forcing state `1`,
kicking the queued head, or bypassing CdInit would still be a hack.

## 2026-08-27 — exact pinned product falsifier

The exact Clang product built against recorded psxport `99a42aa3` dispatched the retail entry,
installed the measured VSync HLE, and reached IRQ/CD initialization. It produced no first present or
visible X11 window within the 20-second bounded run, so there is still no frame or live menu evidence.
The exact launched PID was terminated with the scoped safe-kill helper and confirmed gone. The run
also rejected a persisted `native` render request and resolved it to GTE; that proves capability
resolution but does not advance the CD frontier. The next honest observation remains the bounded
`[0x8009B734,0x8009B780)` state watch above.

## 2026-08-27 — finite native frame-owner implementation (not yet product-verified)

The title boundary now has a source-complete finite driver rather than dispatching `0x80028BA0` as
an unbounded guest loop. It retains the generated bodies as registered supers, runs the measured two-
initializer boot prefix once, and exposes one bounded iteration to `FrameLoopShell`. The title-owned
iteration preserves the measured prior-buffer presentation callback, CD/XA state-machine, buffer/
geometry/OT setup, mode dispatch, and OT splice order. The replaced `0x800296C4` barrier still runs
its timer snapshot, conditional OT compaction, PRNG update, and callback guard effects; its one finite
RCntCNT2 turn is delivered through the shipping BIOS event owner as class `0xF2000002`, spec `2`, so
registration/enabled state and interrupt-context register preservation are not duplicated. A missing
event release is a named fatal contract failure. The replaced display init retains the measured body
except its leading VSync call. `0x800859A8` is now declared as the typed protected VSync address, with
no `Timing::vsyncHle` binding.

The direct-runtime pad layout is also measured rather than inferred: `FUN_800B0B9C` initializes two
42-byte title pad records and passes their `+2` receive buffers to linked libpad initialization, giving
slot 0 `0x800A9132` and slot 1 `0x800A915C`. The frame barrier publishes host packets through the
shared pad service immediately before RCntCNT2 event delivery, so the retained guest callback's
`0x800291D8 -> 0x80029DC0` pad parse consumes the current packet.

An earlier focused Clang compilation of the frame-loop/runtime targets completed before the final
retail-body corrections and `FrameLoopShell::prepareProduct` integration. It is useful prior evidence,
not evidence for the current tree. A current product build, focused CTest, product execution, and
clang-tidy remain deliberately unclaimed until they actually complete; the existing exact product
falsifier above therefore still governs live status.

The integration comparison against shipping-emitted `gen_func_80028BA0` caught and corrected two
source transcription defects before product launch. After the mode call, the retail body restores
`v0=0x800B0000`; the finite body now does the same. More importantly, the two `0x8007BAB0` OT-splice
calls consume the guest pointers stored at `0x800A9218` and `0x800ADD54`, not those variables'
addresses. The frame contract now seeds distinct pointer values and asserts all six splice arguments,
so substituting either address cannot pass the production-seam test.

## 2026-08-27 — first finite-driver product run and first residual owner

The current Clang product installed one fatal sync primitive, resolved the renderer to GTE with PC
enhancements locked out, dispatched the finite boot prefix, and aborted before any frame/presentation
fence. This is a successful ownership falsifier, not a working-game result:

```text
GUEST VSYNC VIOLATION: reached 0x800859A8 a0=-1 ra=0x80083940 pc=0x800859A8
```

The generated/native backtrace is `0x80083904 <- 0x80083E4C <- 0x800844F0 <- 0x8008F958 <-
0x8008EBD8 <- 0x8006AB64 <- 0x800B0548`. Ghidra decompilation and the exact
`[0x80083904,0x80083B84)` disassembly agree that `FUN_80083904` is Tekken's linked `CdSync`; its two
`VSync(-1)` calls only arm/check a 960-field timeout around the response drain. The live call hit the
first query even though `DAT_80099A30` was already ready (`2`).

The first implementation removed the timeout calls but retained the asynchronous controller drain.
The real product falsified it immediately: CdControl had no synchronous response yet, so removing its
clock could not make the underlying asynchronous operation native. That implementation was replaced,
not papered over. `CdSync` and `CdControl` now preserve Tekken's validation, Setloc/Setfilter mirrors,
command/status globals, and return convention while delegating the hardware operation to psxport's
shipping synchronous stock-libcd owner. The generated `gen_func_80083904` and
`gen_func_80083E4C` remain registered supers.

## 2026-08-27 — synchronous controller passed; queue VSync owners exposed

Two serialized real-disc product runs advanced the fatal VSync frontier without weakening the trap:

- PID `3135550`: synchronous `CdControl` completed, then `FUN_80090F78` called VSync(-1) at return
  address `0x80091050`. Ghidra shows this query only records the start field for a command-group
  timeout after `FUN_8008F08C` accepts the group.
- PID `3141032`: the native `FUN_80090F78` owner passed, then `FUN_80091328` called VSync(-1) at
  return address `0x80091344`. Ghidra shows this query only compares the same start field against a
  1200-field timeout before releasing the group.

Both runs resolved an unsupported persisted Native request to GTE and reached no frame, present, or
audio sample. PID `3141032` overlapped another title's process, so it is frontier evidence only, not
isolated product verification. Both PIDs exited on the intentional trap and were confirmed absent.

`game/core/cd_sync.*` now owns both queue functions using `Game::timing.vblank`—the counter advanced
only by the native frame owner—in place of their VSync(-1) queries, while retaining queue allocation,
callbacks, timeout/cancel behavior, release behavior, guest globals, register ABI, and generated
supers. This current second queue owner is Clang-built and focused-contract green but not yet live-
verified. No guest VSync binding exists; any unowned caller still aborts by construction.

## 2026-08-27 — isolated queue-result run exposes the response-poll owner

The canonical Clang tree was rebuilt and verified against clean, pushed psxport `3c342ec3`: full
CTest 15/15, C++ policy formatting/size 25/25, clang-tidy 17/17, and the provenance check passed.
Isolated real-disc PID `3172936` then proved both native queue owners execute through the result
release path. It exited itself before a frame because the protected VSync trap correctly rejected the
next unowned caller:

```text
GUEST VSYNC VIOLATION: reached 0x800859A8 a0=-1 ra=0x80083BC0 pc=0x800859A8
```

The exact generated/native chain is `FUN_80091328 -> FUN_8008F5CC -> FUN_8008FC4C ->
FUN_80083B84 -> VSync`. `FUN_80083B84` is Tekken's response-ready poller. Exact generated code and
the prior complete xref census show both callers use non-blocking mode 1, but the function still calls
VSync(-1) before checking the completion-class byte at `0x80099A32` and acknowledgement-class byte at
`0x80099A31`; its only use for time is the 960-field asynchronous drain deadline.

Native CD commands already finish synchronously before this poll. `CdProtocol::ready` therefore owns
the same title response priority, clears the consumed status byte, copies the corresponding eight-byte
response (`0x800A3BE8` before `0x800A3BE0`), and returns zero when neither response is ready. It neither
calls VSync nor creates another CD hardware owner; the exact generated `gen_func_80083B84` remains the
registered super. The hermetic contract covers acknowledgement copying, completion priority, status
consumption, and the no-VSync invariant. The focused Clang product build, contract 2/2, and clang-tidy
17/17 pass. This new owner is not yet product-verified; no relaunch was authorized after the diagnosis.

PID `3172936` is absent. The run produced no present and a zero-byte WAV, so no frame, widescreen
image, menu, or gameplay is claimed.

## 2026-08-27 — response poll passes; retained asynchronous queue is falsified

Isolated PID `3185894` ran the product with the native `CdReady` owner for roughly 45 seconds and
made no guest VSync call. It then exited on the boot-progress watchdog with the exact active chain
`FUN_80091328 <- FUN_80091E5C <- FUN_80091858 <- FUN_80091558 <- FUN_8006AB64 <- FUN_800B0548`.
No frame/present occurred and the WAV remained zero bytes.

This falsifies the first queue implementation at its ownership boundary. It replaced the queue's
VSync timestamps with `Game::timing.vblank` but retained `FUN_8008F08C`'s asynchronous command group.
During the finite boot prefix the native frame loop has not started, so that field counter remains
zero; more importantly, the retained per-sector callbacks never decrement `DAT_8009B890` under the
synchronous native controller. `FUN_80091E5C` therefore polls a positive remaining-sector count
forever. Raising the watchdog or advancing a fake clock would hide the cause, not complete the read.

Ghidra supplies the closed call domain: `FUN_80090F78` and `FUN_80091328` each have exactly one direct
caller, `FUN_80091E5C`. That caller converts its LBA to a `CdlLOC`, then passes `(location, sector
count, destination)` to the queue; its three callers use the result as a synchronous boolean read.
The replacement queue owner now calls psxport's shared `cd_control_sync` Setloc bookkeeping and
`cd_read_stock_sync` real-disc transfer, publishes zero remaining sectors on success or `-1` on
failure, and returns without allocating or releasing an asynchronous guest command group. This is the
same synchronous ownership boundary as the native CdControl/CdSync path, not a fabricated completion:
success is published only after the real requested sectors are in guest RAM.

The expanded hermetic contract proves the exact location/count/destination reach the read owner,
success publishes zero, failure publishes `-1`, busy requests do not start another read, and no guest
VSync is called. Focused Clang build, product link, contract, and clang-tidy 17/17 pass. This fully
synchronous queue owner has not yet been driven in another authorized product run.

## 2026-08-27 — synchronous read passes; blocking TOC command wrapper exposed

Isolated PID `3196289` opened the real Tekken 3 CHD and advanced beyond the synchronous directory
read with no guest VSync call. The boot-progress watchdog then captured a new active chain:

```text
FUN_80090D88 -> FUN_8008F3DC
  <- FUN_80090DF8 <- FUN_8006AB64 <- FUN_800B0548
```

`FUN_80090DF8` enumerates the disc TOC through GetTN (`0x13`) and GetTD (`0x14`). Its callee
`FUN_80090D88(command, parameters, result)` allocates a generic asynchronous command and spins in
`FUN_8008F3DC` until the returned status becomes nonzero, accepting only status 2. This is the same
invalid ownership split as the retired data queue: a blocking guest command group cannot be the
completion owner under synchronous native CD.

The native `FUN_80090D88` owner now routes the original command ABI through `CdProtocol::control` and
returns its boolean success contract. GetTN/GetTD result bytes are derived from the opened CHD's actual
`DiscState` track metadata: first/last track for GetTN, and track-start or lead-out MSF for GetTD.
This preserves the TOC data the caller parses instead of acknowledging with fabricated zero bytes.
The exact generated body remains its registered super. Canonical Clang product build, full CTest
15/15, verify, psxport `3c342ec3` provenance, and clang-tidy 17/17 all pass. This owner is not yet
product-verified.

PID `3196289` exited itself and is absent. No frame/present occurred and its WAV is zero bytes.

## 2026-08-27 — TOC commands pass; ResetGraph exposes the GPU timeout clock

Isolated PID `3216829` opened the real CHD, passed the synchronous directory-read and GetTN/GetTD
owners, and reached Tekken's ResetGraph path with no earlier guest VSync. The product printed
`ResetGraph:jtb=80098b70,env=80098bb8`, then the protected VSync trap captured the next unowned call:

```text
GUEST VSYNC VIOLATION: reached 0x800859A8 a0=-1 ra=0x8007E900 pc=0x800859A8
FUN_8007E8F0 <- FUN_8007E154 <- FUN_8007C528 <- FUN_800B07C8
  <- FUN_800B07A8 <- FUN_800B07A0 <- FUN_800B0794 <- FUN_800B0788 <- FUN_800B0548
```

The exact generated body and Ghidra agree that `FUN_8007E8F0` does not wait or submit GPU work. It
only arms the linked GPU queue's timeout by storing `VSync(-1)+240` and clearing a poll counter.
`FUN_8007E924` is the paired poll owner: it compares the same field deadline, retains an independent
`0xF0000` poll-count failsafe, and only on a real timeout logs queue/register state and performs the
measured critical-section, queue, GP1, DMA-channel, and GP0 reset sequence. Queue production and
draining remain in their generated title bodies.

`game/core/gpu_sync.*` now supplies those two clock functions with `Game::timing.vblank`, the native
frame ledger, without calling guest VSync. Its hermetic contract proves the inclusive field boundary,
poll-count fallback, queue-depth report, two critical-section return PCs, and exact reset writes. The
generated `gen_func_8007E8F0` and `gen_func_8007E924` remain registered supers. Canonical Clang build,
CTest 17/17, C++ policy 28/28, clang-tidy 19/19, verify, and exact psxport `3c342ec3` provenance pass
for this GPU owner. It is not yet product-verified.

PID `3216829` exited itself and is absent. It reached no frame or present and its WAV is zero bytes.
The saved evidence is `scratch/logs/tekken3-isolated-toc-3c342ec3.log`,
`scratch/logs/tekken3-isolated-toc-3c342ec3.stdout.log`, and
`scratch/raw/tekken3-isolated-toc.wav`.

The same combined batch closes the product's own help boundary. The Python launcher already handled
`-h/--help` before dependency and asset discovery, but a direct `tekken3_port --help` probe exposed
that the executable treated the flag as a disc path and armed its runtime watchdog. `main.cpp` now
prints product usage and exits zero before constructing `Tekken3Runtime`; a stripped-environment
product contract proves both spellings make no runtime/disc discovery output.

Before the next product run, shared psxport advanced cleanly from `3c342ec3` to `fb08d30f`. Tekken's
pin and canonical Clang build now match `fb08d30f`; CTest 17/17, C++ policy 28/28, clang-tidy 19/19,
the complete `verify` target, and framework provenance all pass. No older product artifact is valid
for the next live claim.

A complete Ghidra xref census closes the measured ResetGraph/display-initialization synchronization
domain before that run. `FUN_8007E8F0` has exactly five callers: GPU DMA submit `FUN_8007D874`, image
load/store `FUN_8007DB84/FUN_8007DDC0`, command queue `FUN_8007E154`, and DrawSync
`FUN_8007E7B4`. Their ten timeout checks all call paired `FUN_8007E924`, so the two native owners cover
every live driver-table path. Three adjacent SDK image helpers (`FUN_8007EB08/FUN_8007EBF4/
FUN_8007ECE0`) inline the same VSync clock but have zero executable references and are not part of the
selected product's caller domain. ResetGraph mode 0 itself initializes the measured driver table at
`0x80098B70` through `FUN_8007E664` without VSync; the subsequent clear reaches table slot +8,
`FUN_8007E154`. Direct display initializer `FUN_800B0954` is already the finite native owner that
retains its body while removing its leading VSync(0). This census leaves no adjacent owned GPU sync
call for the next run to discover one at a time.

## 2026-08-31 — current product reaches presentation, then stalls in the title-loader scene

After rebuilding against shared psxport `8eb9a79e`, a windowless product run with the real CHD completed
1,200 native frames and emitted a presented 960x720 sink image. Frame 1 was black while the display
initialized; frame 119 and frame 1,199 both showed the centered `NAMCO PRESENTS` title card. The run
had no fatal, watchdog, guest-VSync, or dropped-layer report. This is the first observed product
present, but it is not a faithful-release claim: the generated substrate still reports `UNKNOWN`, and
the run never reached a menu or gameplay scene.

The bounded run narrows the next frontier to the title-loader state after the Namco card, not the
frame cadence or GPU timeout owners. Do not raise the frame cap or add a synthetic delay to mask the
stall. The next discriminator must trace the loader's CD request/completion state and compare it with
the independent retail boot, then implement the missing queue callback/event ownership at that measured
boundary.
