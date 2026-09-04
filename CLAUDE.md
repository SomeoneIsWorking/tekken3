# Tekken 3 port

Read `external/psxport/CLAUDE.md`, `external/psxport/docs/workspace/PROTOCOL.md`, and
`../../shared/jit-common/docs/migration.md` before work. Never commit discs, extracted executables,
runtime JIT caches, `.env`, or machine-specific paths. Run artifacts go under `scratch/`, never
`/tmp`; builds go under `build/`.

## Product execution contract

Tekken 3 (`SLUS_004.02`) ships as one native/Lightrec psxport product. The authenticated executable
is runtime data. Image-and-address-keyed native overrides own selected verified functions; a pinned
Lightrec integration dynamically executes every remaining guest instruction. A native override's
original call suppresses only that override for one call and executes the guest body by address
through Lightrec. psxport owns machine-state synchronization, HLE/device callbacks, override
invalidation, executable-memory invalidation, and bounded exits; Lightrec owns its code cache and
executable memory.

An interpreter is permitted only in a separately built test/diagnostic target. The gameplay product
must not link it, expose a selector for it, or fall back to it. No offline, build-time,
install-time, or provisioning-time step emits guest C/C++, object code, or a precompiled title
substrate. Do not generate, build, or run the static path during migration.

The first implementation discriminator is `NAMCO PRESENTS` within 1,200 frames with nonzero
Lightrec execution and all 14 address-based original calls routed through the shipping dispatcher.
That checkpoint does not authorize deletion. Next, drive representative interactive gameplay and
verify rendering, input, audio, timing, relevant invalidation, and released-host performance. Only
that complete gate permits removing the generator, generated corpus, seed manifest, static
dispatcher/bindings, and generated-symbol tests; none remains as a compatibility mode or oracle.

## Product and enhancement boundaries

Tekken 3 already runs at 60 fps. Its rendering-enhancement scope is widescreen only: do not add an
fps60 mode, interpolation/lerp, or temporal state maintained solely for interpolation. Widescreen
work remains RE-driven; bind the measured guest camera/projection/culling owners through the shared
non-temporal guest-widescreen contract. Do not add a title-owned native renderer, and never
reconstruct pictures from GTE/OT/GP0 diagnostic output. Establish a faithful, measurable base before
the widescreen enhancement.

Host ownership follows this project's codemap and cohesive-owner boundary: `game/core/tekken3_runtime.*` is the one
process-lifetime game owner, `game/core/frame_loop.*` owns the finite title frame and its measured
service order, `game/core/tekken3_port.*` composes framework devices around them, and
`game/core/main.cpp` is the narrow player entry point. Probe entry points only parse their inputs,
install the same owner, and drive a separate test target. The runtime derives directly from
`GameRuntime` and owns the measured resident-text range through immutable `GuestProgramImage`;
Tekken source must not include or instantiate `LegacyGameRuntimeAdapter`, `GameConfig`, or
`GameHooks`.

`external/psxport` is a symlink to the workspace's shared framework clone when one exists, or a
private clone at this repo's `psxport.pin` on a fresh machine. `tools/psxport_sync.py --auto`
establishes whichever applies; `psxport_sync.py --bump` records the framework commit this game is
built and verified against, and `--check` fails when the built framework is not the recorded pin.
Framework edits happen in the shared clone (`$PSX/psxport`), never here.

`./run.sh` is the shipping zero-argument player contract: a slim `uv run --frozen` shim into
`bootstrap.py` and `tools/run.py`. The Python initializer provisions and identity-checks the user's
disc executable, builds `tekken3_port`, and launches only the native/Lightrec product. It must not
run tests, probes, diagnostics, static generation, or an interpreter. CMake owns compiler discovery;
the launcher must not add compiler-identity allowlists, denylists, or forced compiler selections.
