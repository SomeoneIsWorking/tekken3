# Tekken 3 project state

This is the factual capability inventory. Epic intent lives in `docs/project-goals.md`, atomic work
in `docs/issues/`, ownership and placement in `docs/codemap.md`, and ordered reverse-engineering
dependencies in `docs/re-frontier.md`.

| ID | Capability / observable outcome | State | Dependencies | Goals |
|---|---|---|---|---|
| S001 | The selected USA disc executable is reproducibly identified and provisioned | verified | — | G001, G003 |
| S002 | Retail entry and direct-main startup execute deterministically to an independent boundary | verified | S001 | G001, G003 |
| S003 | A shipping Tekken 3 product is derived from the resident executable substrate | partial | S001, S002 | G001, G003 |
| S004 | Boot and CD initialization are compared across independent or distinct execution engines | partial | S002, S003 | G001, G003 |
| S005 | The title declares a non-temporal, guest-rendered widescreen capability contract | partial | S003 | G002 |
| S006 | Tekken-owned projection, display, visibility, and clipping state is identified for widescreen | partial | S001 | G002 |
| S007 | True widescreen renders additional correctly projected content | missing | S004, S005, S006 | G002 |
| S008 | Product frames, input, audio, and gameplay execute correctly | missing | S003, S004 | G001 |
| S009 | The default launcher delivers the playable widescreen product | missing | S007, S008 | G001, G002, G003 |

## Current focus

S004 is the current focus: product execution has passed native CD/TOC initialization and now owns the
first linked GPU queue timeout clock; drive that owner through ResetGraph toward the first frame.

## Capability details

### S001 — selected executable identity and provisioning

Evidence: C001/C002 and I001/I002 record the USA `SLUS_004.02` path, full-file identity, PS-X EXE
header, disc extent, extraction route, controlled disagreement cases, and a verified real extraction.
`titles/tekken3/executable.json` is the measured authority and `tools/provision_executable.py` keeps
all extracted bytes under gitignored `scratch/`.

### S002 — deterministic retail startup boundary

Evidence: C003/C004 and I003/I004 establish the direct `entry -> game_main` structure from executable
bytes and Ghidra, then compare psxport and an independent Mednafen CPU at the call boundary. Both
engines are deterministic and agree on 35/35 CPU fields; forced disagreement and too-short execution
are refused.

### S003 — shipping generated product substrate

The player composition installs `Tekken3Runtime`, derives resident functions from the identity-checked
executable, loads that executable, binds framework devices, and dispatches the retail entry.

Gap: A built whole-program target and saved product traces do not prove a completed frame or gameplay.
The isolated `3c342ec3` product PID `3216829` dispatched the retail entry, opened the real CHD, and
passed the synchronous directory-read and GetTN/GetTD owners. It then reached ResetGraph and trapped
the next protected guest VSync query in linked GPU timeout armer `FUN_8007E8F0`. Its exact PID exited
and is confirmed gone. The resulting native-ledger GPU arm/poll owner is combined-gate green but not
yet product-verified. A later 1,200-frame windowless run against the real CHD produced a presented
sink image and the `NAMCO PRESENTS` title card, but the generated substrate still reports `UNKNOWN`
and no menu or gameplay scene is covered.

### S004 — differential boot and CD initialization

Independent Mednafen and generated execution agree on 35/35 CPU fields at five startup boundaries
through Tekken's DPCR access. A controlled Getstat/INT3 boundary separately compares the executable
interpreter with shipping-emitted C and agrees on 34/34 CPU values, 38/38 unique RAM bytes, and 4/4
CDC fields for both a publishing response and a non-publishing control.

Gap: The independent CPU now continues through DPCR and the measured context-save path, but cannot yet
execute B(19) HookEntryInt and return for another two-engine comparison. Whole-product execution now
passes CD/TOC initialization with no guest VSync call and reaches ResetGraph. Issue 0011 records the
exact GPU timeout-arm chain and the combined-gate-green native field/poll owner for
`FUN_8007E8F0/FUN_8007E924`. No frame or gameplay is covered.

### S005 — title render-capability contract

`Tekken3Runtime::renderCapabilities()` returns the shared `widescreenOnly()` policy. The runtime seam
checks GTE as the only player-selectable path, PSX as a supported diagnostic path, Native as
unsupported, and temporal interpolation as unsupported.

Evidence: The shared capability implementation is recorded at `psxport.pin` `fb08d30f`. The exact
Clang gate passes CTest 17/17, clang-tidy 19/19, and the 13/13 capability seam. A bounded product run
also rejected a persisted `native` selection as unsupported and resolved it to GTE.

Gap: The product did not reach a first present or create an X11 window, so the absence of Native and
60fps Interpolation rows remains static-only and is not visually verified in the actual menu.

### S006 — measured widescreen owners

C012/I007 and `tools/verify_projection.py` identify the complete six-writer CR24/CR25/CR26 census,
the view-dimension and projection-centre chain, focal-length owner, both display presets, stage
visibility angles, and rendering-path right-edge comparisons on the hashed executable.

Framework commit `2e840231` now decodes Tekken's GP1 368-pixel mode generically. The title's
`Tekken3Widescreen` owner binds the measured 384x480-view/368-draw and 320x240/320 facts to the shared
projection plan, then uses the same resolved guest draw width for the stage/effect primitive
clippers while retaining their generated 4:3 supers. The hermetic contract proves the wide
384->512 projection and x=400/450 added-margin cases.

Gap: These owners have not been driven in a completed gameplay frame or A/B-tested against a faithful
4:3 image. The first presented frame is currently the title-loader card, not a completed gameplay
frame. The separate 600/780 stage-tile visibility wedge remains measurement-dependent: a real wide
frame must show whether it requires a derived frustum adjustment.

### S007 — true widescreen output

Missing capability: no completed Tekken frame has demonstrated wider guest geometry, stage/effect
coverage, and final presentation while preserving vertical framing and the faithful 4:3 control.

### S008 — frames, input, audio, and gameplay

Missing capability: the product has not completed and visually presented a frame, accepted verified
gameplay input, produced verified title audio, or sustained gameplay.

### S009 — default playable widescreen product

Missing capability: `./run.sh` builds and launches the intended product, but that product does not yet
satisfy the observable frame, gameplay, or widescreen conditions of S007 and S008. Launcher and direct
product `-h/--help` contracts both exit zero before dependency, runtime, or disc discovery.
