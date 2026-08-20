# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: the USA target executable can be provisioned and its direct-to-main startup shape is
verified, but the project is still a framework scaffold. No extracted executable is tracked, no game
seam or generated substrate exists, and no boot, native producer, widescreen path, or interpolation
path is claimed yet.

## Configure the framework scaffold

Configure with Clang before the first verification or after changing CMake inputs:

```sh
python3 tools/psxport_sync.py --auto
CCACHE_DISABLE=1 cmake --fresh -S . -B build \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++
```

The normal gate builds the scaffold, checks the recorded framework pin, runs the shared first-party
`clang-format` / `clang-tidy` / source-size policy, exercises both-answer executable/startup tool
selftests, and executes the framework smoke test:

```sh
CCACHE_DISABLE=1 cmake --build build --target verify
```

There is no game translation unit yet, so the shared policy's explicit scaffold mode reports honest
zero-file format, size, and lint denominators. It begins checking files as game code is added.

`tekken3_scaffold` and its smoke test only prove that the game-agnostic framework links. They do not
launch Tekken 3. See `titles/tekken3/README.md` for the measured target and
`docs/re-frontier.md` for the ordered work required before a boot claim is possible.

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
