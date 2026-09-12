---
id: 11
title: Native/Lightrec product stops before its first completed title frame
status: investigating
symptom: the current Lightrec product exhausts its first-frame guest-call budget inside the title decompressor
state_items: S003,S004,S008
tags: runtime,cd,title-loader,t3-04
created: 2026-08-25
updated: 2026-09-12
---

## Current boundary

The current Lightrec product has no completed title frame. An earlier bounded headless run of the
already linked Clang-built `build/ci/bin/tekken3_port` (SHA-256
`3e2259031b97f72208148a379450b4b4a952b6dae746f8ec55ed68b672ed0719`, build receipt
`psxport=8b2103294b68e082eef8fe64bb3e972da21bec09`) opened the authentic CHD, completed the
finite main prefix, initialized the 960x720 Vulkan sink, then aborted in the first
`FrameLoop::step` guest call: `budget-exhausted` at `0x80031C78` after 564,482 cycles. The cap was
1,200 frames, but zero frame ends completed; no `NAMCO PRESENTS` or loader-wait observation was
possible. The linked binary was not rebuilt while the shared framework was being edited.

Ghidra places `0x80031C78` in `FUN_80031BFC`, the title's LZ-style decompressor. The disassembly
at `0x80031C78..0x80031C90` copies a bounded back-reference run (`lbu` source, `sb` destination,
`slt` length, branch back). Five direct call sites use this decompressor: one static-resource
initializer (`FUN_800484F4`) and four image-loading wrappers (`FUN_8004C6FC`, `FUN_8004C7E4`,
`FUN_8004C91C`, `FUN_8004CA40`). That earlier error record did not identify which call site,
compressed input, or output position was active. The framework's `ExecutionBudget::currentTurn`
allows 33,868,800/60 cycles for each guest call while the title's `guest::call` requires a completed
return. Thus the current evidence cannot distinguish a legitimately long decompression from a
wrong input/loop state; raising the budget or treating the exit as a completed call would assume
the answer.

One new bounded shipping-product run used Clang-built `build/ci/bin/tekken3_port` (SHA-256
`66eecab8c9cff36c4c2c8cf96c5780489300dcd05038ce9a7aaa32822594ef02`, linked against
psxport `13806e8156376e8e1dd86c43b70a89b44c61598d`) with the authenticated executable and
CHD, one requested frame, headless Vulkan, no audio device, and no pacing. PID `85388` exited and
was confirmed absent. At the actual `guest::call` failure boundary, the title-local shipping
diagnostic reported the outer guest call `0x800B0708`, outer return `0x80028C9C`, and an exit inside
the decompressor at `0x80031C78` after 564,482 cycles. Its live `ra=0x8004CA9C` identifies the
`FUN_8004CA40` image-loading wrapper. Live `a0/source=0x800BC2D0`, `a1/destination=0x8012B223`,
`a3/back-reference=0x8012B21D`, and `t1/output-start=0x8012867C` all mapped to main RAM. The
output pointer was 11,175 bytes beyond its preserved start, with 883,076 mapped bytes remaining;
the active back-reference copy had completed `1/11` bytes and read six bytes behind its destination
within the format's 2,048-byte bound. The probe classified one of one sampled exits inside the
decompressor; its synthetic controls separately produced one reached, one unreached, one valid,
and one invalid-bound result through the same formatter. It cannot measure compressed-source
consumption because Lightrec exposes no decompressor-entry sample at this title-local boundary.

This proves mapped, bounded copy state at that instant, not the function's eventual return or a
correct compressed payload. The direct binary run omitted `PSXPORT_ASSET_DIR`, so the overlay
reported missing UI assets before this CPU stop; no presentation conclusion follows. The process
returned status `139`; the log shows the budget error followed by a watchdog signal-06 backtrace,
but no saved core for PID `85388` was found, so the cause of status `139` remains unproven. Zero
title frames completed.

The operator repeated the bounded retail run after pinning psxport `1d7701cc` and passing the
combined Clang gate. This run supplied the framework UI assets and kept normal pacing; it loaded
all four Rml assets, entered the first native-owned frame, and reported the same `0x80031C78`
budget exit after 564,482 cycles. The live output was again 11,175 bytes from its start, with a
`1/11` back-reference copy at distance six and mapped source/destination pointers. The process
again returned status `139` after the watchdog's signal-06 backtrace. No title frame completed;
the new run confirms the decompressor boundary under the current framework, not its eventual
progress or output correctness.

The authenticated `SLUS_004.02` text was re-imported at `0x80010000` from the provisioner-verified
SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` and queried
through Ghidra. This narrows one concrete loader wait but does **not** establish that the current
Lightrec product reached it. `FUN_80052A70` returns byte `0x800A069F`; its caller
`FUN_80052CC4` waits while the return is nonzero. `FUN_800529CC` starts the underlying loader:
`FUN_8006BF20` queues its asset extent, and `FUN_8006C084` sets the wait byte to `1` before
submitting command `0xA0` through `FUN_8008F08C` with request-mode argument `6` and callback
`FUN_8006C26C`. The current title CD overrides do not own that `FUN_8008F08C` command path.

The callback chain distinguishes completion from error. `FUN_8006C26C` registers
`FUN_8006C2A0` with `FUN_80091F38` only on class `2`. `FUN_8006C2A0` consumes one 0x800-byte
sector on class `1`, decrements the outstanding byte count, advances the destination, and clears
`0x800A069F` after the last queued extent. Its class-`5` error branch records loader failure state
`9` and leaves the wait byte set. Ghidra's narrow disassembly confirms the byte set at
`0x8006C1A4` and the clear at `0x8006C410`. The code makes either a missing sector callback or a
class-`5` error a possible permanent wait; only live callback/result evidence can choose between
them and a different stalled title state.

The retired generated-source runner's last bounded real-CHD run completed 1,200 native fields and
emitted a 960x720 sink image. Field 1 was black while display state initialized; fields 119 and
1,199 showed the centered Namco card. The run reported no fatal, watchdog, guest VSync, or dropped
layer. This is historical presentation evidence, not evidence that the current native/Lightrec
product reached the card.

## Grounded preceding owners

- The retail entry reaches CD initialization. Getstat responses return `0x02`; retained boundary
  evidence records agreement on 34 CPU values, 38 distinct RAM bytes, and four CDC fields for the
  normal response path, including init step `0x16 -> 0x17`. That retired measurement is evidence,
  not a current product gate.
- Tekken's linked `CdSync` (`FUN_80083904`) and controller wrapper (`FUN_80083E4C`) preserve title
  validation, command/status globals, mirrors, and return ABI while delegating the hardware operation
  to psxport's synchronous stock-libcd owner.
- `FUN_80090F78` and `FUN_80091328` have one direct caller, `FUN_80091E5C`; the synchronous queue
  owner transfers the requested sectors before publishing success and never manufactures a clock or
  completion.
- `FUN_80090D88` routes blocking GetTN/GetTD through the synchronous controller and derives result
  bytes from the opened CHD's measured track metadata.
- GPU timeout armer `FUN_8007E8F0` and poller `FUN_8007E924` use `Game::timing.vblank` rather than
  guest VSync. A complete Ghidra xref census covers five armer callers and ten paired checks across
  GPU DMA, image transfer, command queue, and DrawSync.

Isolated PID `3216829` opened the real CHD, passed the synchronous directory and TOC paths, reached
ResetGraph, and exposed the GPU timeout clock at return PC `0x8007E900`. Its measured chain was:

```text
FUN_8007E8F0 <- FUN_8007E154 <- FUN_8007C528 <- FUN_800B07C8
  <- FUN_800B07A8 <- FUN_800B07A0 <- FUN_800B0794 <- FUN_800B0788 <- FUN_800B0548
```

The native timeout owner and the subsequent 1,200-field run crossed that boundary without weakening
the protected VSync trap. PID `3216829` exited and was confirmed absent.

## Ruled-out shortcuts

- Advancing a synthetic clock, raising the watchdog, or increasing the field cap would conceal the
  stalled state rather than complete the missing title transition.
- Publishing fabricated success before requested sectors are in guest RAM violates the synchronous
  read contract.
- Forcing CD state, kicking a queue manually, or bypassing callbacks would skip the lifecycle whose
  ownership is under investigation.
- The earlier inference that CD-system state had failed was too strong: a trace excluded ready state
  `1` at one sample but did not distinguish initializing state `2` from failed state `3`.

## Next discriminator

The first sampled image resource made 11,175 bytes of bounded output progress before the call's
single-turn budget expired. Ghidra decompiled both `FUN_8004CA40` and `FUN_80031BFC` (2/2 requested
functions) and disassembled 16/16 instructions in `0x8004CA70..0x8004CAB0`: the wrapper's current
eight-byte table entry is `s1`, its table base is `s3`, `lw a0,4(s1)` executes at `0x8004CA8C`,
and the `jal FUN_80031BFC` delay slot adds `s3` to form the compressed-source entry. `s5` supplies
the output start. At return address `0x8004CA9C`, the wrapper checks whether the returned output
length exceeds `0x8240` (33,344 bytes). This is a maximum, not an exact resource length. The
decompressor stops at a zero control byte, so exact encoded output length depends on the live
source bytes. No saved log contains `s3`/`s1`, and no numerical source entry or encoded extent can
be claimed from the previous runs.

The title-local shipping exit probe now checks the live reached-wrapper register/table invariants,
reconstructs the source entry, and scans only mapped RAM through the zero control byte, bounded by
the wrapper's output limit read from its actual guest instruction. It reports a source-consumed
denominator and encoded output extent only if the scan terminates, cursor/output progress fits, and
source/output spans do not overlap. Missing reach, invalid table/instruction, truncated input, and
unterminated input report their negative result and scanned count; focused synthetic controls pass.
An authenticated headless, silent retail run after the 11/11 Clang gate reached the wrapper at
`0x8004CA9C`: table base `0x800B8D58`, entry index 2/127, encoded source
`0x800BAFCC`, and destination `0x8012867C`. The bounded scan found the zero terminator after
7,772 source bytes and described 21,524 output bytes under the wrapper's 33,344-byte cap.
At the typed `BudgetExhausted` exit at `0x80031C78` (564,482 cycles), the guest had consumed
4,868/7,772 source bytes and produced 11,175/21,524 output bytes. The scan reported
`complete consistent=1`; no frame had completed. The watchdog's signal backtrace follows the
intentional failed-call abort, so the product still does not boot. This is evidence of remaining
finite encoded input, not proof that Lightrec's output or guest state agrees with an independent
oracle. Compare this exact stream and the continued guest state with that oracle before classifying
the budget as too short or the data/execution as wrong.
First resolve this guest-call exit; frame-end loader sampling cannot observe a run with zero
completed frames.

After the native/Lightrec product reaches the Namco-to-menu boundary, the next title-loader check is
the measured loader state below. Its binary ownership is established, but its live reachability is
still unknown:

Capture `0x800AE204` (mode), `0x800AE224` (phase), loader wait `0x800A069F`, outstanding bytes
`0x800A06A4`, destination `0x800A06A8`, raw-command queue count `0x800A3E40`, callback pointer
`0x8009B8D0`, callback class, and final loader state `0x800A05D8` across the card-to-menu boundary
in an independent retail run and the native/Lightrec product. Report both reached and not-reached
answers for `FUN_8006C26C` and `FUN_8006C2A0`, including request and callback denominators.
Implement only the first measured missing owner, then rerun the same bounded boundary; do not add a
delay, phase write, or scene-pointer shortcut.
