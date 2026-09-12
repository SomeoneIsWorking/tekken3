# Tekken 3 RE frontier

Statuses: `re-verified` means binary/disc ground truth plus executable verification; `re-partial`
names an honest remaining gap; `todo` is not started. No hacks are tracked.

## Execution migration gate

The product execution owner is native psxport code plus a pinned Lightrec integration. The
authenticated `SLUS_004.02` image is loaded as runtime data; Lightrec executes every guest body not
selected by the image-and-address-keyed native override table. An override's original call returns
to that address through the dynarec while suppressing only the current override. The gameplay binary
has no selectable interpreter engine. Lightrec may automatically interpret only bounded blocks the
JIT refuses; the shipping run must report those blocks by reason and instruction count and enforce a
release threshold. The retired local interpreter probe is absent; forced interpretation and an
interpreter oracle remain test-only.

The first implementation discriminator is `NAMCO PRESENTS` within 1,200 frames, nonzero Lightrec
block execution, and all 14 address-based original calls observed through the shipping dispatcher.
It must also exercise relevant invalidation, bounded exits, timing/interrupt/device synchronization,
and an override/original-call positive and controlled negative. This checkpoint is followed by a
representative interactive gameplay scenario with correct input, audio, rendering, timing, and
declared host-architecture performance.

## Boot spine

### T3-01 — Select and measure the target executable
- status: re-verified
- deps:
- evidence: C001/I001. The USA disc's `SYSTEM.CNF` names `cdrom:\TEKKEN3\SLUS_004.02;1`; `discdump list` reports that nested file at LBA 25 with 1,185,792 bytes. A fresh extraction has SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c`. The Clang-built shipping `crt0_extract` reports PS-X EXE entry `0x80079C70`, load `0x80010000`, text size `0x121000`, extent `[0x80010000,0x80131000)`, and eight resolved structural startup fields. Ghidra independently decompiled the entry and first JAL target; a narrow post-decompile disassembly confirms `jal 0x80028BA0` at `0x80079D04` with a `nop` delay slot. The target is the non-returning game main loop, not libcInit.
- where: `titles/tekken3/README.md`; untracked extraction and Ghidra project under `scratch/`
- gap: None for executable identity and the measured entry boundary. This does not prove runtime guest execution or a booting port. Framework issue #2 records why the decoder's generic `libcInit` label is not semantic evidence here.
- notes: All disc-derived files remain gitignored. The target hash is over the complete 0x121800-byte PS-X EXE, including its 0x800-byte header.

### T3-02 — Provision the selected disc and executable reproducibly
- status: re-verified
- deps: T3-01
- evidence: C002/I002. `tools/provision_executable.py` resolves CLI > `PSXPORT_TEKKEN3_DISC` > `.env` > one root CHD without falling through from a bad configured path, extracts the nested `TEKKEN3/SLUS_004.02`, and checks eight tracked identity/header facts from `titles/tekken3/executable.json`. Its shipping-path selftest passes 12/12 positive, byte-mismatch, malformed-executable, preservation, ambiguity, and refusal cases. A real USA CHD extraction produced 1,185,792 bytes with SHA-256 `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` under `scratch/bin/tekken3/`.
- where: `tools/provision_executable.py`; `titles/tekken3/executable.json`; gitignored `.env` or root drop-in input
- gap: None for reproducible executable provisioning. Disc provenance beyond the selected measured image remains outside this tool's claim.

### T3-03A — Model Tekken's direct-to-main startup boundary
- status: re-verified
- deps: T3-02
- evidence: C003/I003. `tools/verify_startup.py` checks the real executable's first entry call `0x80079D04 -> 0x80028BA0`, nop delay slot, immediate break-on-return guard, both initializer calls and delay words, the first initializer's exact return, and `0x80028E0C -> 0x80028BCC` main-loop back-edge without using the framework's `libcInit` name. It passes 10/10 agreement/disagreement/refusal fixtures and 18/18 structural facts on the provisioned USA executable. A fresh Ghidra 12.0.4 decompile of `FUN_80079c70`, `FUN_80028ba0`, and `FUN_80079d10` on the same hashed RAM image confirms the entry/main relationship and first initializer semantics.
- where: `tools/verify_startup.py`; `titles/tekken3/executable.json`; `titles/tekken3/README.md`
- gap: None for executable structure. T3-03 separately tests execution to this boundary; neither step
  proves Lightrec execution or a booted frame.

### T3-03 — Preserve the deterministic entry-boundary evidence
- status: re-partial
- deps: T3-03A
- evidence: C004/I004 preserve the historical result: two psxport-interpreter runs and two independent vendored-Mednafen runs agreed on all 32 GPRs, HI, LO, and PC (35/35 fields) at `0x80028BA0`; the independent oracle reached it at step 106153.
- where: `docs/info/claims/004-tekken-3-psxport-and-independent-mednafen-execut.md`; `tools/verify_startup.py`; `titles/tekken3/executable.json`
- gap: The retired interpreter probe is not a current gate. Replace it with a bounded Lightrec-versus-independent-oracle discriminator before treating execution at this boundary as re-verified; this still does not prove `game_main`, BIOS/devices, a frame, or gameplay.

### T3-04 — Execute through the native/Lightrec product discriminator
- status: re-partial
- deps: T3-03
- evidence: The retained observations in this frontier prove the exact first initializer, next call,
  and observed second-initializer chain, including function-table dispatch 0x80085BC8 -> 0x80085D5C.
  Independent Mednafen and the retired measurement runner agreed on all 35 CPU fields at 0x80079D10,
  0x80028BB8, 0x800B0548, post-store
  0x80085D98, and the measured DPCR boundary 0x80085DB4. The shared oracle's vendored IRQ
  controller executes the selected executable's exact I_MASK-write/read and I_STAT-write sequence on
  that same CPU, reports the WRITE32 to DPCR 0x1F8010F0 at 0x80085DB0 with value 0x33333333, and
  continues through the measured context-save path to a strict pre-BIOS capture at 0x80085DE4; the
  retired second execution path independently observed that store. The retained
  GPUSTAT negative case still stops, and the isolated Mednafen IRQ process still agrees with the
  retired second execution path on 3/3 observations at 0x80085DA4. That run additionally executed the
  measured B(19) return through `FUN_80086264` (1050-word clear), `FUN_800862D8`
  (callee-saved context save), and the B-vector stub `FUN_800862C8` (`li t2,0xB0` / delay
  `li t1,0x19` / `jr t2`) to the caller return `ra=0x80085DEC`, with framework HLE modeling kernel
  function B(0x19) HookEntryInt; SELFTEST 11/11 includes missing-note and wrong-function refusals at
  that edge. Boundary SELFTEST 11/11, IRQ SELFTEST 2/2, and framework oracle 43/43 detect
  register/source/boundary/hardware-register/device errors.
- where: `game/core/tekken3_runtime.*`; `game/core/guest_execution.*`;
  `game/core/frame_loop.*`; historical `scratch/raw/t3-04/oracle.trace`
- gap: The authenticated Lightrec product now completes its first title frame after six bounded
  suspensions of the 127-resource mode call (issue 0011), with 360,083 executed blocks and zero
  interpreter fallback in a natural seven-field run. It has not reached representative gameplay.
  Exercise the wired executor and image-aware override/original-call bindings through the 1,200-frame
  `NAMCO PRESENTS` discriminator above. Existing comparison evidence also leaves one
  generic owner before another independent two-engine boundary: because `oracle_trace` maps no BIOS,
  an independently sourced B(19) HookEntryInt model (or mapped BIOS execution) must return the same
  CPU before comparing at 0x80085DEC. Issue #10 records why an older unbounded trace's later
  `0xFFFF8C94` access is garbage execution, not a hardware frontier. Copying psxport's B(19) HLE into
  the reference would destroy independence. No next real hardware boundary is known until that owner
  lands. The first completed frame does not establish later DMA behavior or gameplay.
  Separately, the whole-product path reaches Tekken's first directory-read request but starves its
  four-command queue before Pause issues: issue #11's saved provisioned run proves
  `FUN_80090F78` returned into `FUN_80091E5C`, while static RE proves the queue executor is skipped
  whenever CD-system state `DAT_8009B750` is not ready state `1`. The trace does not distinguish
  initializing state `2` from failed state `3`. The retained controlled INT3/Getstat measurement
  agrees on 34/34 CPU values, 38/38 unique RAM bytes, and 4/4 CDC fields and proves the normal path
  publishes `0x02` and advances init step `0x16 -> 0x17`. Its retired execution mechanisms are not
  current product inputs or gates. The remaining
  discriminator is live IRQ-context state across current command, route table, callback pointer/class,
  and CD state. The next serialized run watches `[0x8009B734,0x8009B780)`; forcing the state or queue
  kick is not a fix. The exact `99a42aa3` product run on 2026-08-27 reconfirmed this literal frontier:
  retail entry dispatch and IRQ/CD initialization occurred, but no first present or X11 window was
  produced within 20 seconds. Its exact PID was safely terminated and confirmed gone.
  The later isolated `3c342ec3` product PID `3172936` advanced through both native queue owners and
  into the result-release chain, then correctly tripped the protected VSync fatal in response-ready
  poller `FUN_80083B84` at return address `0x80083BC0`. The title now has a readable native owner for
  that poller's completion-before-ack response contract; its hermetic contract is green, but the owner
  has not yet been driven in another authorized product run. No frame or presentation is covered.
  PID `3185894` subsequently passed that response owner with no guest VSync call and falsified the
  retained asynchronous queue itself: before the native frame loop starts, neither its native field
  deadline nor its guest per-sector callback count can advance. The replacement uses the shared
  synchronous Setloc/CdRead owners for the sole `(location,sectors,destination)` queue call domain and
  publishes success only after real disc bytes reach RAM. Its focused contract is green but it is not
  yet product-verified.
  PID `3196289` passed that read owner, opened the real CHD, and made no guest VSync call. Its watchdog
  backtrace exposed the next retained asynchronous owner: generic blocking command wrapper
  `FUN_80090D88` spinning in `FUN_8008F3DC` for GetTN/GetTD. The new owner routes commands through the
  synchronous native protocol and derives TOC bytes from actual CHD track metadata. It is combined-
  gate green and PID `3216829` subsequently passed it. That run reached ResetGraph and exposed the
  next protected VSync query in GPU timeout armer `FUN_8007E8F0`, through the exact chain
  `8007E8F0 <- 8007E154 <- 8007C528 <- 800B07C8 <- 800B07A8 <- 800B07A0 <- 800B0794 <- 800B0788
  <- 800B0548`. Retained instruction evidence and Ghidra show the call only stores a 240-field deadline and
  clears a poll counter; paired `FUN_8007E924` checks that deadline, retains an independent `0xF0000`
  poll failsafe, and performs the linked queue/GPU/DMA reset only on timeout. The new cohesive owner
  sources the deadline from the native frame ledger, preserves that failsafe/reset sequence, retains
  both authenticated original guest bodies, and is combined-gate green against current pinned psxport `fb08d30f` but not
  yet product-verified on that framework. PID `3216829`
  exited itself; no frame, present, or audio sample was produced.
  A complete Ghidra xref pass closes this measured sync domain: the five live callers of the armer and
  all ten calls to the poller are the resident driver-table DMA/image/queue/DrawSync owners; the three
  SDK helpers that inline the clock have zero executable references. ResetGraph mode 0 and its driver
  initializer contain no VSync, and direct display initializer `FUN_800B0954` is already natively
  owned. Those measurements bound the native owners required on the dynamic path; they do not
  authorize bypassing the native/Lightrec discriminator above.
- notes: Ghidra identifies the observed path as `FUN_800b0548 -> FUN_80055884 -> FUN_80079964/FUN_800799a8`,
  then indirect `FUN_80085bc8 -> FUN_80085d5c`. The retained run preserved that indirect dispatch
  instead of replacing it with a direct call. That result remains execution evidence rather than a shipping
  implementation requirement. `Tekken3Runtime` owns the framework seam directly and carries the measured
  resident range in immutable `GuestProgramImage`; no adapter/config/hooks view remains. Its boundary-only
  policy explicitly returns `guestVramIsPicture=false`: no rendered picture exists yet, and the
  widescreen path must coordinate guest geometry, draw coverage, and final sampling rather than
  claiming an unproven framebuffer. This ownership policy does not advance or bypass the execution
  boundary.

## Widescreen ownership and enhancement

### T3-05 — Identify the widescreen projection owner
- status: re-partial
- deps: T3-04
- evidence: C012/I007. Static analysis of the complete hashed `SLUS_004.02` image plus Ghidra decompilation identifies all six canonical CR24/CR25/CR26 writes. `FUN_80080a40` owns the title's view dimensions; `FUN_80081148` derives the retail projection centre from those dimensions; `FUN_80080da8` publishes the centre plus the current double-buffer offsets through `SetGeomOffset` at `0x80082728`. `FUN_80063c64` clamps the title-owned focal length and publishes it through `SetGeomScreen` at `0x80082748`; `FUN_80064080` selects a six-field fight-camera pose containing that focal length and `FUN_80064170` blends between authored poses. The two resident display presets prove that title view/projection width is distinct from the active PSX display width: the boot preset owns a 384x480 view and OFX/OFY 192/240 while its active display rectangle is 368x448; the alternate preset owns 320x240 and OFX/OFY 160/120. Both initialize H=500. The first measured widescreen owner after the current `FUN_8006AB64` CD wedge is `FUN_800B0840(0)` at `0x800B0574`; it routes preset 0 through `FUN_80080848` to dimension owner `FUN_80080A40` before deriving the centre and H. The stage owner `FUN_8006D014` supplies horizontal visibility angles 600/780 to the 6x6 tile selector `FUN_8006D95C`; stage/effect primitive clippers `FUN_8006CC28` and `FUN_8006E44C` contain eleven plus one rendering-path signed `-368` right-edge comparisons. `tools/verify_projection.py` now proves 38/38 facts on the real executable and passes 8/8 real agreement, mutated disagreement, and refusal cases. Those bounds must widen with the resolved display plan; the separate player-select text-slide use remains 2D retail layout.
- where: `tools/verify_projection.py`; `titles/tekken3/executable.json`; `titles/tekken3/README.md`; Ghidra project and decompilation under gitignored `scratch/`
- gap: Framework commit `2e840231` fixed the generic 368-mode decoder and `game/core/widescreen.*` now binds the measured dimension and clipping owners to one guest-wide plan. A real 4:3/wide visual A/B remains gated on the native/Lightrec product reaching representative gameplay. OT, GP0, and GTE output are diagnostic evidence, never producer input.

### T3-06 — Owned widescreen
- status: re-partial
- deps: T3-05
- evidence: `Tekken3Widescreen` publishes the shared plan at `FUN_80080A40`, preserves vertical extent/H ownership, widens the view 384->512 at 16:9, and feeds the corresponding 492-pixel draw width to readable wide-only ports of the two measured stage/effect clippers. The 4:3 route calls each authenticated original guest body through Lightrec. `tekken3_widescreen_contract` proves both measured display/view pairs plus stage/effect primitives in the added margin.
- where: `game/core/widescreen.*`; `tests/widescreen_contract.cpp`; shared `guest_widescreen_projection.*`
- gap: The product still has no completed frame, so final sampling, 4:3 pixel identity, and actual added scene coverage are unverified. A real A/B must also determine whether the authored 600/780 stage-tile visibility wedge culls needed wide-margin tiles; any adjustment must derive from the resolved projection. Tekken 3 already runs at 60 fps: there remains no native renderer, fps60 mode, interpolation/lerp, or interpolation-supporting temporal pipeline in this title's target scope.
