# Tekken 3 project state

Epic intent lives in `docs/project-goals.md`, ownership and placement in `docs/codemap.md`, atomic
work in `docs/issues/`, and what has and has not been reverse-engineered in `docs/re-frontier.md`.

| ID | Capability | State | Evidence or gap |
|---|---|---|---|
| S001 | The selected USA disc executable is reproducibly identified and provisioned | verified | `titles/tekken3/executable.json` plus `tools/provision_executable.py`; extracted bytes stay under gitignored `scratch/` |
| S002 | Retail entry and direct-main startup execute deterministically to an independent boundary | verified | direct `entry -> game_main` from executable bytes and Ghidra; psxport and an independent Mednafen CPU agree on 35/35 CPU fields |
| S003 | The authenticated executable runs through the native/Lightrec gameplay product | partial | 1,054,867 presented fields, `translated_blocks=1956`, `fallback: calls=0`, `faults=0`; blocked at the NAMCO PRESENTS card (issue 0020, T3-04) |
| S004 | Boot and CD initialization are compared across independent or distinct execution engines | partial | 35/35 at the entry-to-main boundary; the independent CPU still cannot execute B(19) HookEntryInt and return (issue 0010) |
| S005 | The title declares a non-temporal, guest-rendered widescreen capability contract | partial | `TitleRuntime::renderCapabilities()` returns the shared `widescreenOnly()` policy; not yet seen in the running menu (issues 0012, 0013) |
| S006 | Tekken-owned projection, display, visibility, and clipping state is identified for widescreen | partial | CR24/CR25/CR26 writers, view and focal-length owners, both display presets and the stage wedge decoded; no product frame has exercised them |
| S007 | True widescreen renders additional correctly projected content | missing | the frame to widen does not exist yet: mode 3 lives in the runtime-written handler window (issue 0022) and the card blocks before it (issue 0020) |
| S008 | Product frames, input, audio, and gameplay execute correctly | partial | one 368x480 frame captured at field 24,782; the image is still the title card, and no pad-driven frame exists |
| S009 | The default launcher delivers the playable widescreen product | missing | `./run.sh` provisions, builds and launches, but the product meets neither the S007 nor the S008 condition |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | `.github/workflows/ci.yml` runs `tools/verify.py`; composition only |
| S011 | Load operations complete without loading-only waits or presentation | missing | no Tekken 3 load operation has been enumerated yet |

## Current focus

S003 — own the CD completion chain in `game/cd/cd_protocol.cpp` so the guest's per-sector callback at
`0x8009213C` actually runs and the card clears itself (issue 0020).