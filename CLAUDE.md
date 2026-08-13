# Tekken 3 port

Read `external/psxport/CLAUDE.md` and `external/psxport/docs/workspace/PROTOCOL.md` before work.
Generated code is sacrosanct. Never commit discs, extracted executables, `generated/`, `.env`, or
machine-specific paths. Run artifacts go under `scratch/`, never `/tmp`.

All picture work is RE-driven. Widescreen and interpolation require PC-native graphics producers
reading game state; do not reconstruct pictures from GTE/OT/GP0 output. Establish a faithful,
measurable base before enhancements.
