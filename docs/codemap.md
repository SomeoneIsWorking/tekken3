# Codemap

Structural authority for the Tekken 3 port. Every directory, namespace, class and free function the
product ships is listed here, followed by the ownership chains for the flows a defect hides inside.
Epic intent lives in `docs/project-goals.md`, the capability inventory in `docs/project-state.md`,
atomic work in `docs/issues/`, and the binary-evidence chain in `docs/re-frontier.md`.

The framework side of every chain lives in the sibling checkout `external/psxport` (a relative
symlink to the live workspace framework, or a clone of its `main`); its own map is
`external/psxport/docs/codemap.md`.

## Shape

```text
run.sh -> bootstrap.py -> tools/run.py -> game/entry/main.cpp
                                          |
                                          v
                              game/entry/product_launch.cpp   tekken3::launchProduct
                                          |
            psx::Machine (framework)      |      tekken3::TitleRuntime (game/program)
                                          v
                        game/frame/finite_frame.cpp  tekken3::frame::FrameDriver
                          one field turn, one guest frame, per field

separate test target -> independent oracle (never linked or selectable by the gameplay product)
```

`game/` is the only first-party include root, so a header is reached by its subsystem path
(`#include "frame/finite_frame.h"`, `#include "cd/loader_lifecycle.h"`).

## game/entry — process entry and product composition

| Symbol | Kind | Responsibility |
|---|---|---|
| `game/entry/main.cpp` | `main()` | Parse `--help`, construct the title runtime on the stack, hand it to the launcher. Prints usage on stdout before any runtime or disc discovery. |
| `tekken3::launchProduct` | free function (`game/entry/product_launch.h`) | Install the runtime, build `Game`, `watchdog_init` + `load_exe`, compose `psx::Machine` (bind devices, render path, `prepare`), run the finite boot prefix, attach the control channel, run the field loop. |
| `tekken3::kUnattendedFieldCap` | `constexpr` | The field cap an unattended headless run gets when no bound was requested and no window exists. |

## game/program — executable facts and framework-facing title policy

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::program::kEntry`, `kResidentPhysicalLo`, `kResidentPhysicalHi` | `inline constexpr` | Authenticated `SLUS_004.02` mapping facts: retail entry and resident physical text extent. Data, never generated guest code. |
| `tekken3::ResidentProgramRange` | struct | The measured resident text extent handed to the runtime by the boundary harness. |
| `tekken3::TitleRuntime` | class (`GameRuntime`) | Process-lifetime title policy: render capabilities (`RenderPath::Record` by default, no native path, no interpolation), the pad-buffer layout, the widescreen projection, the immutable `GuestProgramImage`, override registration, boot dispatch, and creation of the title frame driver. Owns the `widescreen::WidescreenProjection`. |
| `tekken3::hle::plan()` | free function (`game/program/platform_hle_plan.h`) | The one immutable `PlatformHlePlan` this title declares: the measured linked-libetc VSync entry, the guest field word a negative query answers from, and the single admitted body window. Data only — never a handler. |

## game/frame — the finite boot prefix and the one title frame

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::frame::Machine` | abstract class | The injectable machine boundary: guest calls, registers, memory, ticks, event delivery, and the three per-field services (`commitPresentation`, `serviceAudioSink`, `servicePad`). Implemented by the shipping `CoreMachine` adapter and by the contract tests' recorders. |
| `tekken3::frame::StepState`, `tekken3::frame::Stage` | struct, enum | What a field must remember across fields: the boot stage (first initializer, second initializer, running), whether a spanning guest call (initializer or mode body) is still running, and which buffer it was building. |
| `tekken3::frame::FiniteFrame` | class (static) | The finite frame itself, reproduced from the guest bodies it replaces: `runBootPrefix` (the non-returning `0x80028BA0` prologue), `stepBoot` (the two retail initializers `0x80079D10` and `0x800B0548` as spanning calls), `runBarrier` (`0x800296C4`, one RCntCNT2 delivery, pad publication), `runDisplayInit` (`0x800B0954` without its VSync wait), and `step` (the field). |
| `tekken3::frame::FrameDriver` | class (`::FrameDriver`) | The title driver psxport calls once per field. Registers the three native frame entries (`installOverrides`), runs the finite boot dispatch once (`runBootPrefix`), and advances the field (`stepFrame`). Holds the `psx::cpu::ResumableGuestCall` that spans an initializer or mode body across fields; each host turn gets `FiniteFrame::kFieldTurnCycles` (one NTSC field of emulated time), because a half-field turn puts a CD deadline on the VBlank that flushes it. |

## game/execution — the finite guest call

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::execution::GuestCallEntry` | struct | Register snapshot at a guest-call boundary: address, return PC, `a0`-`a3` and `t1`. |
| `tekken3::execution::FiniteGuestCall` | class (static) | The one finite guest call this title makes, and the only account of one that did not return. |
| `…::FiniteGuestCall::callToReturn` | static | One display field through the product dispatcher, required to return, refused with the full account when it does not. |
| `…::FiniteGuestCall::describe`, `…::captureEntry` | static | Turn a non-returning exit into one log line: where the guest stopped, how far the LZ decompressor had read and written, and the image-wrapper entry it belongs to. |

## game/cd — the decoded loader lifecycle

The guest's own linked libcd runs the whole command, interrupt and completion chain. CD reads are
instant, so the module's one behaviour is `sector_ready_order`, which restores the order the guest's
libcd assumes (class-2 completion before the first sector's INT1) without any drive timing. The rest
is facts about the chain.

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::loader::*` | `inline constexpr` facts (`game/cd/loader_lifecycle.h`) | The decoded guest CD-read lifecycle: loader state block, the untimed wait the card sits in, the chain record and its callback slot, the dispatch of that slot, and the sector callback that clears the wait byte. Pinned against the executable by `tests/loader_lifecycle_contract.cpp`. |
| `tekken3::cd::completeReadBeforeSector`, `serviceInterruptsBeforeFlush`, `chainCompletionApplies`, `installOverrides` | functions over `cd::Machine` (`game/cd/sector_ready_order.{h,cpp}`) | Native overrides of the ready hook `FUN_8008F850`, the INT flush `FUN_800842E0` and the class-2 completion `FUN_8006C26C`: deliver the pending class-2 completion before a sector is handed to the callback slot, run the CD ISR before the flush discards a pending INT1, and drop a late class-2 completion once the load is idle. Tested by `tests/sector_ready_order_contract.cpp`. |

## game/render — the linked-libgpu queue timeout

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::render::QueueMachine` | abstract class | The narrow queue boundary: the guest field counter, guest memory, the critical-section guest call, and the timeout report. |
| `tekken3::render::armDeadline` | free function | Arm the queue deadline from the guest VBlank field counter. |
| `tekken3::render::pollQueue` | free function | Poll the deadline; on expiry report the queue and reset it, returning -1. |
| `tekken3::render::installOverrides` | free function | Install the two native timeout entries (`gpuTimeoutArm`, `gpuTimeoutPoll`). |

## game/widescreen — the widening projection and its clippers

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::widescreen::policyFrom` | free function | The runtime's own projection policy reached from `Core`; an override that cannot find it refuses. |
| `tekken3::widescreen::WidescreenProjection` | class (`GuestWidescreenProjection`) | Latch the widened view for the guest (`publishDimensions`), report the presentation aspect, and clip stage and effect primitives against the widened draw width. Installs the view-dimension and two clipper entries. |
| `tekken3::widescreen::StageTileWedge` | class | The last horizontal culling owner: reproduce the 6x6 stage-tile selection for a wedge widened in the tangent domain (`widenWedge`), falling through to the retail body when the plan did not widen. Installs the tile-selector entry. |

## game/fieldclock — the guest VBlank field word

| Symbol | Kind | Responsibility |
|---|---|---|
| `tekken3::field::kEntry`, `kBodyEnd`, `kCounter` | `inline constexpr` | The measured linked-libetc VSync leaf, the half-open end of its body, and the guest VBlank field count a negative mode returns. |
| `tekken3::field::readCounter` | free function | The one production binding of that measured word to guest RAM. |

## tools, titles, tests

| Path | Responsibility |
|---|---|
| `run.sh`, `bootstrap.py`, `tools/run.py`, `pyproject.toml`, `uv.lock` | The player's zero-argument path: provision and identity-check the USA executable, build, launch. |
| `tools/psxport_fetch.py` | Establish `external/psxport` (workspace symlink, else a shallow clone of `main`). |
| `tools/provision_executable.py` | Extract and identity-check `SLUS_004.02` into gitignored `scratch/`. |
| `external/psxport/tools/port/launch_environment.py`, `external/psxport/tools/dbgclient.py`, `external/psxport/tools/formats/psx_exe.py` | The shared launch policy, live-endpoint client and PS-X EXE reader every title tool imports. A tool that re-implements one of these owns a copy that can disagree with the product it measures. |
| `tools/verify.py` | The asset-free product gate: configure, build, run every title contract, check the linked execution boundary. |
| `tools/ghidra_query.py`, `tools/probe_loader_state.py`, `tools/probe_cd_completion.py`, `tools/probe_tekken3_widescreen_pair.py` | Maintainer RE tools used by the open issues; none is a gate. |
| `tools/verify_vsync_field_clock.py`, `tools/test_*.py` | Gates: the field word the product ships vs. what the executable measures, and the launcher/product help contracts. |
| `titles/tekken3/executable.json`, `titles/tekken3/README.md` | Identity, load map, startup facts, projection facts. |
| `tests/` | One contract per owner, built as separate targets and never linked into the product. |

## Who owns it

### The frame turn

1. `tekken3::launchProduct` (`game/entry/product_launch.cpp`) calls `psx::Machine::run`.
2. `psx::Machine::run` loops `psx::Machine::stepFrame` — the **framework** owns the loop and its cap.
3. `psx::Machine::stepFrame` runs `psx::FieldTurn::beginField` (pause/step, watchdog re-arm) — the
   framework's services around the field.
4. `psx::FrameLoopShell::step` calls the title's `tekken3::frame::FrameDriver::stepFrame` and takes
   the frame capture that enforces one presentation per field.
5. `tekken3::frame::FrameDriver::stepFrame` calls `tekken3::frame::FiniteFrame::step` through a
   `tekken3::frame::CoreMachine` adapter, which is where every guest call, register write and
   per-field service of step 6 actually happens.
6. `FiniteFrame::step` runs, in order: the frame barrier (`runBarrier`), the presentation and audio
   commit, the CD/XA state call, the buffer and geometry selection, the mode body (as a
   `ResumableGuestCall` that may span fields), and the ordering-table splice.
7. `psx::FieldTurn::endField` (RAM dump, one queued control command), then back to step 3.

**While a mode call is suspended** (a mode body outlived the field that started it), `FrameDriver`
holds the pending `ResumableGuestCall`, and each further field calls
`FiniteFrame::step`'s pending branch: pad service, presentation commit, audio service, resume. The
field turn still belongs to `psx::Machine`; the title only supplies the body.

**Boot is the same turn once.** `TitleRuntime::bootInit` calls `FrameDriver::runBootPrefix`, which
dispatches the retail entry and is released when the native override at `FiniteFrame::kMain` takes
over and asks for a host transfer. There is no second boot path.

### Host input → guest pad buffer

1. `psx::input::HostInput::drainEvents` (`external/psxport`) is the one host event drain; it owns the
   key state, the gamepads, and the overlay/game keyboard arbitration.
2. `psx::input::Pad::pollHostInput` resolves that state into the active-low button mask and applies
   the debug pause/step keys. It is the one pump, reachable from several sites.
3. `psx::input::Pad::serviceFrame` — called by the title through
   `tekken3::frame::Machine::servicePad` — resolves forced/REPL/replay input, records or replays,
   and **writes the guest packet into the slot buffers**.
4. The two slots come from this title: `TitleRuntime::guestPadBufferLayout` returns
   `0x800A9132` and `0x800A915C`, the receive buffers `FUN_800B0B9C` hands to linked libpad.
5. `FiniteFrame::runBarrier` calls `servicePad()` immediately before the RCntCNT2 event, so the guest
   parses this field's packet rather than a stale one. A held field (pending mode call) calls
   `servicePad()` too, which is why input stays live while a mode body spans fields.
6. The debug/control channel is a separate path into the same state: `psx::DbgServer` is attached by
   `psx::Machine::attachControlChannel`, and `psx::FieldTurn::endField` services exactly one queued
   command per field, so a `quit`, a `mem` read or a pad drive lands between fields and never
   inside a guest call.

### Guest draw → presentation

1. The guest's own GTE and ordering tables produce primitives; nothing here reconstructs them.
2. `tekken3::widescreen::WidescreenProjection::publishDimensions` is the guest's view-dimension entry:
   it latches the shared `GuestProjectionPlan` (`gpu_vk_latch_guest_projection`) and hands the
   widened view back to the retail body, which draws the real field.
3. `StageTileWedge::selectTiles` is the last horizontal culling owner; it runs before the field's
   primitives are built and reproduces the guest's selection for the widened wedge.
4. `WidescreenProjection::clipStagePrimitives` and `clipEffectPrimitive` are the two clipper entries
   the guest calls with a command buffer; they drop what the widened frustum cannot show.
5. The GPU device (Beetle `gpu.c`) executes every GP0 command; `Gp0RecordTap` appends each to the
   field's `FrameRecord`.
6. `psx::FramePresenter::commit` — reached through `tekken3::frame::Machine::commitPresentation` —
   seals the record, presents and paces the field. On `RenderPath::Record` (this title's default,
   `TitleRuntime::renderCapabilities`) `RecordRasterizer` replays the record into the VRAM image;
   at 16:9 `gpu_vk_latch_record_display` adds a margin per side of the 368-wide display (62 columns)
   as a canvas around the buffer. `psx::FrameLoopShell::step` then enforces one presentation per
   field. `PSXPORT_DEBUG=recordcheck` compares each present with the device.
7. Tekken 3 runs at 60 fps, so there is no 60 fps in-between path and no temporal state: the title
   declares `temporalInterpolation = false`. Widescreen is the only rendering enhancement in scope.
   Issue 0023 records why the margins are still black on the record path.

### CD and streaming

1. The guest's loader issues a read: `FUN_8006C084` sets the wait byte `0x800A069F` and registers
   the completion callback `FUN_8006C26C` (`tekken3::loader::*` names both).
2. The guest's own libcd queues Setloc/Setmode/ReadN and writes the controller
   (`psx::cdc_native`, `runtime/psx/cd/cdc_native.cpp`). Reads are instant: ReadN's INT3 and the
   first sector's INT1 are pending before the guest's VBlank timer callback (`FUN_8008FDE8` ->
   `FUN_8008E928`) can deliver the class-2 completion, so `game/cd/sector_ready_order.cpp` delivers
   that completion itself before the sector reaches the ready hook, and runs the ISR before the
   command writer's flush (`FUN_8008FCC0` -> `FUN_800842E0`) can discard the INT1.
3. That completion (`FUN_8006C26C`, class 2) installs the sector callback `FUN_8006C2A0` through
   `FUN_80091F38`. The guest's CD ISR (`FUN_80084A30`) is reached through the libapi interrupt
   dispatcher; for each INT1 it calls the ready hook `FUN_8008F850` -> `FUN_80092034`, which calls the
   sector callback.
4. The sector callback reads the data FIFO by DMA3 (`FUN_80084838`, a polled burst), advances the
   record's destination and remaining bytes, and when the record is done clears the wait byte at
   `0x8006C2EC`, so the guest's untimed spin at `FUN_8006BEA8` exits on its own signal.
5. Interrupts are delivered only at guest function entries outside native overrides
   (`psx::Hle::irqPoll`), so every guest call that waits on the CD runs as a spanning call:
   `FrameDriver` runs both retail initializers and every mode body through `ResumableGuestCall`.

### Audio

1. The guest advances its own sound state inside the frame's barrier callback; `XA` state is driven
   by the frame's `kCdXaState` call, so no host thread owns the guest's audio clock.
2. `tekken3::frame::Machine::serviceAudioSink` — `game.spu_audio.frame()` — is the only host audio
   service the title performs, once per field, after the guest has produced that field's samples.
3. A held field (pending mode call) also calls it, so audio does not stutter while a mode body spans
   fields.

### The debug/control channel

1. `tekken3::launchProduct` calls `psx::Machine::attachControlChannel` before the field loop starts,
   so a driven run and an unattended cap can never race.
2. `psx::DbgServer` owns the loopback endpoint; queued commands are serviced once per field by
   `psx::FieldTurn::endField`, never inside a guest call.
3. Nothing in this title reads the channel directly: `tools/probe_loader_state.py`,
   `tools/probe_cd_completion.py` and `tools/probe_tekken3_widescreen_pair.py` are external clients.

## Where does X go?

- Product composition or the process entry: `game/entry/`
- Executable facts, title policy, or the framework HLE declaration: `game/program/`
- Frame ordering, the finite boot prefix, or anything that must happen once per field:
  `game/frame/`
- A guest call that must return, or the account of one that did not: `game/execution/`
- CD command/response/completion behaviour, or the decoded loader lifecycle: `game/cd/`
- The GPU queue deadline: `game/render/`
- Title projection, clipping, or stage-tile visibility: `game/widescreen/`
- A new measured fact about the guest field clock: `game/fieldclock/`
- New guest instruction semantics, machine synchronization, bounded exit, invalidation, the frame
  loop shell, the field turn, the control channel, input, or presentation: shared `external/psxport`
- A new executable-derived fact: `titles/tekken3/executable.json`, checked against the hashed
  executable by `tools/provision_executable.py`.
- A new measurement about where guest code or data lives: `tools/ghidra_query.py` against the
  imported image, recorded as a named constant in the owning module.
- Epic product scope: `docs/project-goals.md`; verified/partial/blocked/missing capability:
  `docs/project-state.md`; atomic work: `docs/issues/`; binary-evidence order: `docs/re-frontier.md`.
