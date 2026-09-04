# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

The factual capability inventory and current focus live in `docs/project-state.md`; the ordered
binary-evidence dependency chain lives in `docs/re-frontier.md`. Tekken 3 (`SLUS_004.02`) already
runs at 60 fps, so this port exposes no fps60/interpolation option and no native-renderer option. Its
rendering target is the measured guest path plus true widescreen.

## Build and launch the player

Install `uv`, CMake, Git, a compatible C/C++ toolchain, SDL3, SDL3_image, FreeType, and zstd. Then
pass the USA CHD, set `PSXPORT_TEKKEN3_DISC`, copy `.env.example` to the gitignored `.env`, or place
one `*.chd` in the repository root:

```sh
./run.sh "/path/to/Tekken 3 (USA).chd"
```

After the disc source has been configured, `./run.sh` with no arguments is the stable default. It
uses the frozen uv environment, resolves the recorded psxport framework, provisions and verifies
`SLUS_004.02`, loads it as runtime data, builds `tekken3_port`, and launches that native/Lightrec
product. It never substitutes the framework smoke target, a test,
or a boundary probe. `./run.sh --prepare-only` exercises the same provisioning and player build
without launching a game process. Ghidra and other maintainer RE tools are not player prerequisites.

## Verify the asset-free product boundary

The canonical gate resolves PSXPort, configures the real product with Clang and Ninja, runs the
shared first-party `clang-format` / `clang-tidy` / source-size policy, exercises every asset-free
title contract, and inspects the linked execution boundary:

```sh
uv run --frozen python tools/verify.py
```

`game/core/tekken3_runtime.*` owns framework-facing game behavior. Its temporary legacy adapter view
has been removed: it derives directly from `GameRuntime`, returns an immutable `GuestProgramImage`
for measured resident text, and exposes null legacy config/hooks/context views.

`tekken3_port` is the only player product. The asset-free gate proves that it links to the shared
Lightrec executor and title-native owners, but it contains no game bytes and therefore claims no
verified frame or gameplay yet.
See `titles/tekken3/README.md` for the measured target and
`docs/re-frontier.md` for the ordered work required before a booted-frame claim is possible.

## Provision the selected executable

Pass the USA CHD directly, set `PSXPORT_TEKKEN3_DISC`, copy `.env.example` to the gitignored `.env`,
or place one `*.chd` in the repository root. The command extracts the nested disc file and refuses
unless all tracked identity and PS-X EXE header fields match:

```sh
cmake --build build --target discdump
python3 tools/provision_executable.py "/path/to/Tekken 3 (USA).chd"
python3 tools/verify_startup.py
```

The output is `scratch/bin/tekken3/SLUS_004.02`. Disc images and extracted executables are never
committed. The startup verifier models the actual `entry -> game_main -> non-returning frame loop`
shape; it does not reinterpret that call as a libc initialization boundary.

Historical interpreter/oracle agreement at the entry boundary remains evidence only. The current
product discriminator must execute bounded guest work through Lightrec and compare it with the
independent Mednafen oracle; the retired interpreter probe is not a current gate.
