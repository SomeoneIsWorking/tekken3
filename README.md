# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: the USA target executable is measured, but the project is still a framework
scaffold. No extracted executable is tracked, no game seam or generated substrate exists, and no
boot, native producer, widescreen path, or interpolation path is claimed yet.

## Configure the framework scaffold

```sh
python3 tools/psxport_sync.py --auto
CCACHE_DISABLE=1 cmake --fresh -S . -B build \
  -DCMAKE_C_COMPILER=/usr/bin/clang \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++
CCACHE_DISABLE=1 cmake --build build --target tekken3_scaffold
```

`tekken3_scaffold` only proves that the game-agnostic framework links. It does not launch Tekken 3.
See `titles/tekken3/README.md` for the measured target and `docs/re-frontier.md` for the ordered work
required before a boot claim is possible.

Disc images and extracted executables are never committed. Provisioning through a gitignored `.env`
or a drop-in file remains the next frontier step.
