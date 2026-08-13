# Tekken 3

PC-native PlayStation port of Tekken 3, built on
[psxport](https://github.com/SomeoneIsWorking/psxport).

Current status: project scaffold only. No game executable, generated code, native producer,
widescreen path, or interpolation path is claimed yet.

## Configure the framework scaffold

```sh
git submodule update --init external/psxport
external/psxport/scripts/sync-submodules.sh
cmake -S . -B build
cmake --build build --target tekken3_scaffold
```

Disc images and extracted executables are never committed. Provision them through a gitignored
`.env` or a drop-in file in the repository root once the target region and executable are measured.
