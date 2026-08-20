# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: the USA target executable is measured, but the project is still a framework
scaffold. No extracted executable is tracked, no game seam or generated substrate exists, and no
boot, native producer, widescreen path, or interpolation path is claimed yet.

## Configure the framework scaffold

Configure with Clang before the first verification or after changing CMake inputs:

```sh
python3 tools/psxport_sync.py --auto
CCACHE_DISABLE=1 cmake --fresh -S . -B build \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++
```

The normal gate builds the scaffold, checks the recorded framework pin, runs the shared
first-party `clang-format` / `clang-tidy` / source-size policy, and executes the framework smoke test:

```sh
CCACHE_DISABLE=1 cmake --build build --target verify
```

There is no game translation unit yet, so the shared policy's explicit scaffold mode reports honest
zero-file format, size, and lint denominators. It begins checking files as game code is added.

`tekken3_scaffold` and its smoke test only prove that the game-agnostic framework links. They do not
launch Tekken 3. See `titles/tekken3/README.md` for the measured target and
`docs/re-frontier.md` for the ordered work required before a boot claim is possible.

Disc images and extracted executables are never committed. Provisioning through a gitignored `.env`
or a drop-in file remains the next frontier step.
