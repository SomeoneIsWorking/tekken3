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
work remains RE-driven; identify the game's camera/projection owner first, add only the native
ownership the measured wide path requires, and never reconstruct pictures from GTE/OT/GP0 output.
Establish a faithful, measurable base before the widescreen enhancement.

Host ownership follows Dusklight's composition boundary: `game/core/tekken3_runtime.*` is the one
process-lifetime game owner, while the probe entry points only parse their inputs, install that
owner, and drive the framework. The runtime derives through psxport's bounded legacy adapter only
because the generated-code router still consumes the measured resident-text range; no Tekken
behavior belongs in `GameConfig` or `GameHooks`, and no new field or callback may be added there.
