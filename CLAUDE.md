# Tekken 3 port

Read `external/psxport/CLAUDE.md` and `external/psxport/docs/workspace/PROTOCOL.md` before work.
Generated code is sacrosanct. Never commit discs, extracted executables, `generated/`, `.env`, or
machine-specific paths. Run artifacts go under `scratch/`, never `/tmp`.

**`external/psxport` is NOT a git submodule** (2026-08-16): it is a symlink to the workspace's shared
framework clone when one exists, or a private clone at this repo's `psxport.pin` on a fresh machine.
`tools/psxport_sync.py --auto` establishes whichever applies; `psxport_sync.py --bump` records the
framework commit this game is built and VERIFIED against, and `--check` fails when the built framework
is not the recorded pin. Framework edits happen in the shared clone (`$PSX/psxport`), never here.

Tekken 3 (`SLUS_004.02`) already runs at 60 fps. Its rendering-enhancement scope is widescreen only: do not add an
fps60 mode, interpolation/lerp, or temporal state maintained solely for interpolation. Widescreen
work remains RE-driven; bind the measured guest camera/projection/culling owners through the shared
non-temporal guest-widescreen contract. Do not add a title-owned native renderer, and never
reconstruct pictures from GTE/OT/GP0 diagnostic output.
Establish a faithful, measurable base before the widescreen enhancement.

Host ownership follows Dusklight's composition boundary: `game/core/tekken3_runtime.*` is the one
process-lifetime game owner, `game/core/frame_loop.*` owns the finite title frame and its measured
service order, `game/core/tekken3_port.*` composes framework devices around them, and
`game/core/main.cpp` is the narrow player entry point. The generated whole-program substrate is
owned by `tools/ensure_recomp.py` and lives only under gitignored `generated/port/`; never edit it by
hand. Probe entry points only parse their inputs, install the same owner, and drive the framework.
The runtime derives directly from `GameRuntime` and owns the
measured resident-text range through immutable `GuestProgramImage`; Tekken source must not include
or instantiate `LegacyGameRuntimeAdapter`, `GameConfig`, or `GameHooks`.

`./run.sh` is the shipping zero-argument player contract: a slim `uv run --frozen` shim into
`bootstrap.py` and `tools/run.py`. The Python initializer provisions and identity-checks the user's
disc executable, emits the resident product, builds `tekken3_port`, and launches only that product.
It must not run CTest, smoke, probes, or diagnostics. CMake owns compiler discovery; the launcher
must not add compiler-identity allowlists, denylists, or forced compiler selections.
