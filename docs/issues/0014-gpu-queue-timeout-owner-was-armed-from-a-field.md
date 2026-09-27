---
id: 14
title: The GPU-queue timeout owner was armed from a field clock nothing in this product advances
status: fixed
symptom: the native owner replacing FUN_8007E8F0/FUN_8007E924 could never time out, and the 21 real guest VSync queries aborted in the framework's protected handler
state_items: S003,S004,S008
tags: runtime,vsync,gpu-timeout,field-clock,t3-04
created: 2026-09-27
updated: 2026-09-27
---

## What FUN_8007E8F0 is

`FUN_8007E8F0` is Tekken's linked **GPU-queue timeout armer**. Its whole body, from the
authenticated image (exact instruction words, `scratch/re/arm_poll_disasm.txt`):

```asm
0x8007E8F0  addiu  sp, sp, -0x18
0x8007E8F4  sw     ra, 0x10(sp)
0x8007E8F8  jal    0x800859A8        ; the linked libetc VSync
0x8007E8FC  _li    a0, -0x1          ; delay slot: a0 = -1, a QUERY, not a wait
0x8007E900  addiu  v0, v0, 0xF0      ; v0 = field count + 240 fields (4 s at 60 Hz)
0x8007E904  lui    at, 0x800A
0x8007E908  sw     v0, -0x733C(at)   ; *(0x80098CC4) = deadline
0x8007E90C  lui    at, 0x800A
0x8007E910  sw     zero, -0x7338(at)  ; *(0x80098CC8) = poll count = 0
0x8007E914  lw     ra, 0x10(sp)
0x8007E918  addiu  sp, sp, 0x18
0x8007E91C  jr     ra
0x8007E920  _nop
```

`FUN_8007E924` is its poller: it re-reads the same field word, and on `deadline < field` (a **signed**
`slt`) or after `0xF0000` polls it calls `FUN_8007A458("GPU timeout, queue %d, stat %08x")` with the
queue depth and the GP0/GP1/DPCR words, then performs the exact reset sequence — queue tail and head
zeroed, `*GP1 = 0x401`, `*DPCR |= 0x800`, `*GP0 = 0x02000000` then `0x01000000` — bracketed by two
`FUN_80085D44` critical-section calls whose return PCs are `0x8007E9D0` and `0x8007EA4C`. It returns
`-1` on timeout and `0` otherwise. All eight guest globals the existing owner names were re-derived
from those displacements and all eight are correct, and both return PCs are the real `jal` return
addresses. The port's arm/poll arithmetic was already faithful.

## The VSync query it arms, and what the query actually returns

`FUN_800859A8` is the linked libetc `VSync(mode)`. Its negative-mode arm is five instructions:

```asm
0x80085A00  bgez  a0, 0x80085A18      ; a0 >= 0 takes the waiting modes
0x80085A04  andi  s1, v0, 0xFFFF      ; delay slot: the waiting modes return the count
0x80085A08  lui   v0, 0x800A
0x80085A0C  lw    v0, -0x5398(v0)     ; v0 = *(0x800A0000 - 0x5398) = *(0x8009AC68)
0x80085A10  j     0x80085B0C          ; straight to the epilogue, returning v0
```

**A negative mode never waits. It returns one word: `0x8009AC68`.**

That word is the guest's own VBlank field count and nothing else. A constant-propagation sweep of the
authenticated text (295,936 instructions scanned) finds **exactly two** stores to it, and both decode
independently to `0x8009AC68` from unrelated `lui`/`sw` pairs:

| site | instruction | what it is |
|---|---|---|
| `0x8008637C` | `sw zero, -0x5398(at)` after `lui at, 0x800A` | the library init zeroing it |
| `0x800863DC` | `sw v0, -0x5398(at)` after `lui at, 0x800A` | the per-vblank callback incrementing it |

The incrementing function is `FUN_800863B0`, which does `DAT_8009AC68 = DAT_8009AC68 + 1` and then
dispatches eight registered per-vblank callbacks. It is installed by `FUN_80086358` (the library
init, whose only caller is `FUN_80085D5C` at `0x80085DF0`) through `FUN_80085BF8(0, FUN_800863B0)`.

**Ghidra's reference model reports ZERO references to `0x8009AC68`.** The accesses use the two-register
`lui`/`lw` form it does not model, so the sweep is the authority for the writer census and Ghidra is
the authority for the read path. Two instruments agreeing here would not have been two facts — this is
the same hole issue 0011 records for `0x8009B750`.

## Why the guest's protected VSync query trapped

`PlatformHle::vsync` (`runtime/psx/platform_hle.cpp:59`) is the framework's mandatory handler for the
leaf, and it is protected by design:

```cpp
if (static_cast<std::int32_t>(core->r[A0]) < 0) {
  if (!owner.mVSyncQueryCounterAddress) {
    lucent::error("plat-hle", "VSync negative query at 0x{:08X} has no measured libetc field counter", ...);
    std::abort();
  }
  core->r[V0] = core->mem_r32(owner.mVSyncQueryCounterAddress);
  return;
}
psx::cpu::requestExecutionExit(*core, psx::cpu::ExecutionExitReason::FrameBoundary);
```

`tekken3::platformHlePlan()` declared `vsyncAddress` and left `vsyncQueryCounterAddress == 0`. So the
trap was a **deliberate framework refusal with no declared answer**, not a mis-recovered instruction:
the title said "this leaf is mine" without saying "and here is the word its negative mode returns".

`FUN_8007E8F0` is only the *first* of the callers that walk into that refusal. There are **22** direct
`jal FUN_800859A8` sites in the authenticated text, and the mode census is:

| mode | count | who |
|---|---|---|
| query, `a0 = -1` | **21** | the two GPU-timeout functions, four GPU DMA/queue functions, seven linked libcd functions (`CdSync`, `CdReady`, `CdDataSync`, …), six VBlank/event functions, and `FUN_800B0954`'s sibling sites |
| wait, `a0 = 0` | **1** | `FUN_800B0954`, the leading `VSync(0)` of the display-init routine |

So the single waiting call site is already owned natively — `FrameLoop::runDisplayInit` reproduces
`FUN_800B0954` deliberately *without* its `VSync(0)` — and the other 21 are pure queries. Declaring the
measured counter is therefore the whole answer, which is a property of this image and not an
assumption: `tools/verify_vsync_field_clock.py` censuses all 22 sites on every run and fails if the
ratio changes, because a new unexamined site is exactly where a wait could hide.

## The real defect, one level down: the native owner's clock was dead

The title already owned the GPU-timeout arm/poll natively (`game/core/gpu_sync.cpp`), and it read its
field clock from `Game::timing.vblank`. **`Nothing in this product advances that counter.****

- `Timing::vblank` is incremented in exactly one place, `Timing::frameTick()`
  (`runtime/psx/timing.cpp:222`).
- `frameTick()` has **no caller** in psxport or tekken3. Tomba! 2's `TombaFrameDriver::stepFrame` calls
  it explicitly; this title's `Tekken3FrameDriver::stepFrame` does not.
- The framework deliberately leaves that advance to the title: `tests/test_frame_loop_shell.cpp:207`
  asserts `frame_loop_shell.cpp` does not contain `timing.frameTick(`.

So the substituted clock was frozen at `0` for the whole run, `arm` always wrote deadline `0xF0`, and
`poll`'s `0xF0 < 0` was never true: **the native GPU-queue timeout could never fire**, while the
retail code it replaced would have fired after 240 real fields. This is the same class of defect
project-state.md already records for the control channel — the title composes its own finite loop
instead of entering `psxport_boot()`, and the one call the spine owned was simply absent.

It was invisible to the gate because `tests/gpu_sync_contract.cpp` handed the protocol a fake machine
whose `fieldCounter()` returned a member the test set by hand. The test proved the *arithmetic*; the
defect was entirely in the *binding* underneath it, and the fake had no binding to be wrong.

## The fix

1. **NEW `game/core/vsync_field_clock.{h,cpp}`** — one owner of the measured facts, with the
   reverse-engineering provenance in the header: the VSync entry `0x800859A8`, its body end
   `0x80085B20`, and the field word `0x8009AC68`. `readFieldCounter(Core&)` is the single production
   binding of that word to guest RAM. It is a read; nothing writes the word.
2. **`game/core/gpu_sync.cpp`** — `CoreGpuSyncMachine::fieldCounter()` now returns
   `vsync::readFieldCounter(core_)` instead of the never-advanced `Game::timing.vblank`. That is the
   faithful substitution: it is the value the retail `jal VSync` / `li a0,-1` pair put in `v0`, so the
   deadline the native owner arms is comparable with the twenty other timeout arms the guest reads the
   same way. The now-unused `game.h` and `<cstdlib>` includes were removed rather than left behind.
3. **`game/core/sync_native.cpp`** — the plan declares `vsyncQueryCounterAddress = 0x8009AC68`, so the
   framework answers all 21 query sites from the same word the title's own owner reads. The entry and
   window literals moved to the new owner instead of being duplicated.
4. **`tools/verify_vsync_field_clock.py`** — parses the shipping header and diffs it against what it
   measures from the authenticated executable, so the constant that ships cannot drift from the
   measurement it came from. It pins three ground-truth instructions before measuring anything, derives
   the address from the instruction words (a hand subtraction during this investigation produced
   `0x800AC68`, wrong by `0x1000`; Ghidra's `DAT_8009ac68` was right), proves the five-instruction
   negative-arm shape, checks both writers, and censuses all 22 call sites.
5. **Tests** — `tests/gpu_sync_contract.cpp` now serves the clock out of the word map at the same
   measured address the product uses, and gains a frozen-word case; `tests/vsync_field_clock_contract.cpp`
   is new and plants three decoy neighbours around the measured word in a real `Core`; `runtime_seam`
   gained the sixth plan fact.

## What this does NOT establish

- **Not verified in a product run.** The machine's product slot was held by the operator for a Spyro
  crash throughout this session, so there is no before/after field or boot evidence here. The unit and
  tool gates are hermetic and real; the product claim is not made.
- **Whether `0x8009AC68` advances in a real run is still open.** It requires the guest's chain
  `FUN_80085D5C` → `FUN_80086358` → `FUN_80085BF8` → `FUN_800863B0` to run, and `FUN_80085BF8` dispatches
  through `+8` of a function-pointer table that `FUN_80085D5C` populates at `+0x14` and `+4` and not at
  `+8`. That last link was not closed statically. It does not affect the fix's correctness — the owner
  reads whatever the retail leaf would have read, and a frozen word now behaves the way retail
  hardware would behave — but it is a real unknown and the honest next measurement.
- `resetGpuQueue` still enters the guest at `FUN_80085D44` through `guest::call`, which requires a
  completed return. Unchanged by this work and untested against a live core.
- The product's next blocker per project-state.md's Current focus is the SIO0 status poll in
  `FUN_80093478`, not this leaf. This fix removes the VSync refusal ahead of it; whether that is the
  last thing between the title and its menu is not established here.
