# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: the USA target executable can be provisioned, its direct-to-main startup shape is
verified, and two independent engines deterministically agree at that call boundary. No extracted
executable is tracked, no generated substrate exists, and no `game_main` execution, frame, gameplay,
native producer, widescreen path, or interpolation path is claimed yet.

## Configure the framework scaffold

Configure with Clang before the first verification or after changing CMake inputs:

```sh
python3 tools/psxport_sync.py --auto
CCACHE_DISABLE=1 cmake --fresh -S . -B build \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++
```

The normal gate checks the recorded framework pin, runs the shared first-party `clang-format` /
`clang-tidy` / source-size policy, exercises provisioning/startup and two-engine boundary selftests,
and executes the framework smoke test:

```sh
CCACHE_DISABLE=1 cmake --build build --target verify
```

The game-owned boundary probe is the first C++ translation unit, so the shared policy checks one
first-party format/size file and one real clang-tidy compile command.

`tekken3_scaffold` and its smoke test only prove that the game-agnostic framework links. The separate
boundary probe runs real Tekken instructions only through the first direct-main call; neither target
launches gameplay. See `titles/tekken3/README.md` for the measured target and `docs/re-frontier.md`
for the ordered work required before a substrate or booted-frame claim is possible.

## Provision the selected executable

Pass the USA CHD directly, set `PSXPORT_TEKKEN3_DISC`, copy `.env.example` to the gitignored `.env`,
or place one `*.chd` in the repository root. The command extracts the nested disc file and refuses
unless all tracked identity and PS-X EXE header fields match:

```sh
cmake --build build --target discdump
python3 tools/provision_executable.py "/path/to/Tekken 3 (USA).chd"
python3 tools/verify_startup.py
python3 tools/boot_oracle.py
```

The output is `scratch/bin/tekken3/SLUS_004.02`. Disc images and extracted executables are never
committed. The startup verifier models the actual `entry -> game_main -> non-returning frame loop`
shape; it does not reinterpret that call as a libc initialization boundary.

The boundary harness executes the entry window twice with psxport's interpreter and twice with the
independent Mednafen oracle. It requires deterministic agreement on all 35 CPU fields after the JAL
delay slot and before `game_main` begins. Its output deliberately excludes generated substrate,
BIOS/device execution, frames, and gameplay.
