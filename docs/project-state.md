# Tekken 3 project state

Epic intent lives in `docs/project-goals.md`, ownership and placement in `docs/codemap.md`, atomic
work in `docs/issues/`, and what has and has not been reverse-engineered in `docs/re-frontier.md`.

| ID | Capability | State | Evidence or gap |
|---|---|---|---|
| S001 | The selected USA disc executable is reproducibly identified and provisioned | verified | `titles/tekken3/executable.json` plus `tools/provision_executable.py`; extracted bytes stay under gitignored `scratch/` |
| S002 | Retail entry and direct-main startup execute deterministically to an independent boundary | verified | direct `entry -> game_main` from executable bytes and Ghidra; psxport and an independent Mednafen CPU agree on 35/35 CPU fields |
| S003 | The authenticated executable runs through the native/Lightrec gameplay product | verified | boot, NAMCO PRESENTS, the intro sequence, the attract loop, the title menu, character select and a fight run to 40,065 presented fields with `faults=0`, `fallback` only `load_delay_hazard` (32,136 single instructions, 0 refused), `recordcheck` mismatched=0 at 4:3 on all of them; the guest's own libcd runs the CD chain with instant CD reads, ordered by `game/cd/sector_ready_order.cpp` (issue 0020) |
| S004 | Boot and CD initialization are compared across independent or distinct execution engines | partial | 35/35 at the entry-to-main boundary; the independent CPU still cannot execute B(19) HookEntryInt and return (issue 0010) |
| S005 | The title declares a non-temporal, guest-rendered widescreen capability contract | partial | `TitleRuntime::renderCapabilities()` selects `RenderPath::Record` with no native path and no interpolation (`tekken3_runtime_seam`); at 4:3 `recordcheck` reports mismatched=0 on 16,534/16,534 presents from boot to a fight (368x480, 368x240 and 256x240 displays); 16:9 margins stay black on the record path (issue 0023); seen in the running title menu, character select and a fight (issues 0012, 0013); the ranking screen and 3D intro scenes show line artifacts (issue 0024) |
| S006 | Tekken-owned projection, display, visibility, and clipping state is identified for widescreen | partial | CR24/CR25/CR26 writers, view and focal-length owners, both display presets and the stage wedge decoded; no product frame has exercised them |
| S007 | True widescreen renders additional correctly projected content | missing | the 4:3 base now reaches the title menu, character select and a fight; no widened frame has been rendered yet (issue 0023 keeps 16:9 margins black on the record path) |
| S008 | Product frames, input, audio, and gameplay execute correctly | partial | Start and Cross taps over the control channel take the title menu to character select, the stage intro and a fight (Xiaoyu vs Yoshimitsu, timer counting); no fight input beyond menu navigation and no audio check yet |
| S009 | The default launcher delivers the playable widescreen product | missing | `./run.sh` provisions, builds and launches, but the product meets neither the S007 nor the S008 condition |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | `.github/workflows/ci.yml` runs `tools/verify.py`; composition only |
| S011 | Load operations complete without loading-only waits or presentation | missing | no Tekken 3 load operation has been enumerated yet |

## Current focus

S008 — drive a fight with pad input and check audio, then S007: bind the measured widescreen owners to the
now-reachable fight frame (issues 0023 and 0024 first).
