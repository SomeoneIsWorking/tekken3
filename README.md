# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: the USA target executable can be provisioned, its direct-to-main startup shape and
first initializer call are verified, and the independent oracle agrees with a six-instruction
generated `game_main` prefix. No extracted executable is tracked, and no initializer execution,
whole generated substrate, frame, gameplay, native producer, widescreen path, or interpolation path
is claimed yet.

## Configure the framework scaffold

Configure with Clang before the first verification or after changing CMake inputs:

```sh
python3 tools/psxport_sync.py --auto
CCACHE_DISABLE=1 cmake --fresh -S . -B build \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++
```

The normal gate checks the recorded framework pin, runs the shared first-party `clang-format` /
`clang-tidy` / source-size policy, exercises provisioning/startup, both oracle boundaries,
generated-source integrity and opposite-answer/refusal selftests, and executes the framework smoke
test:

```sh
CCACHE_DISABLE=1 cmake --build build --target verify
```

The game-owned interpreter and generated-prefix probes are first-party C++ translation units, so the
shared policy checks both with tracked Clang format/tidy configuration and real compile commands.

`tekken3_scaffold` and its smoke test only prove that the game-agnostic framework links. The separate
boundary probes run real Tekken instructions only through `game_main`'s first call delay slot; no
target launches gameplay. See `titles/tekken3/README.md` for the measured target and
`docs/re-frontier.md` for the ordered work required before a whole substrate or booted-frame claim is
possible.

## Provision the selected executable

Pass the USA CHD directly, set `PSXPORT_TEKKEN3_DISC`, copy `.env.example` to the gitignored `.env`,
or place one `*.chd` in the repository root. The command extracts the nested disc file and refuses
unless all tracked identity and PS-X EXE header fields match:

```sh
cmake --build build --target discdump
python3 tools/provision_executable.py "/path/to/Tekken 3 (USA).chd"
python3 tools/verify_startup.py
python3 tools/boot_oracle.py
cmake --build build --target tekken3_recomp_boundary_check -j16
```

The output is `scratch/bin/tekken3/SLUS_004.02`. Disc images and extracted executables are never
committed. The startup verifier models the actual `entry -> game_main -> non-returning frame loop`
shape; it does not reinterpret that call as a libc initialization boundary.

The boundary harness executes the entry window twice with psxport's interpreter and twice with the
independent Mednafen oracle. It requires deterministic agreement on all 35 CPU fields after the JAL
delay slot and before `game_main` begins. The next harness reuses that verified interpreter state,
executes six instructions emitted by psxport's shipping recompiler, and compares all 35 fields before
the first initializer. Its output deliberately excludes initializer and BIOS/device execution,
frames, and gameplay.
