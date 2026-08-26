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

S004 is the current focus: resolve the earliest live CD-initialization state divergence, then resume
the independently compared boot spine toward the first frame.

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
The exact `99a42aa3` product run on 2026-08-27 dispatched the retail entry and reached IRQ/CD
initialization but produced no X11 window or first present within the bounded run. Its exact PID was
terminated and confirmed gone. The generated candidate set includes unexecuted roots; runtime reach
must be established at each real boundary.

### S004 — differential boot and CD initialization

Independent Mednafen and generated execution agree on 35/35 CPU fields at five startup boundaries
through Tekken's DPCR access. A controlled Getstat/INT3 boundary separately compares the executable
interpreter with shipping-emitted C and agrees on 34/34 CPU values, 38/38 unique RAM bytes, and 4/4
CDC fields for both a publishing response and a non-publishing control.

Gap: The independent CPU now continues through DPCR and the measured context-save path, but cannot yet
execute B(19) HookEntryInt and return for another two-engine comparison. Whole-product execution
reaches IRQ/CD initialization and the first directory-read queue but does not issue its commands;
issue 0011 requires a
serialized watch of the real IRQ-context and CD state to identify the earliest divergence. No frame or
gameplay is covered.

### S005 — title render-capability contract

`Tekken3Runtime::renderCapabilities()` returns the shared `widescreenOnly()` policy. The runtime seam
checks GTE as the only player-selectable path, PSX as a supported diagnostic path, Native as
unsupported, and temporal interpolation as unsupported.

Evidence: The shared capability implementation is recorded at `psxport.pin` `99a42aa3`. The exact
Clang gate passes CTest 11/11, clang-tidy 11/11, and the 13/13 capability seam. A bounded product run
also rejected a persisted `native` selection as unsupported and resolved it to GTE.

Gap: The product did not reach a first present or create an X11 window, so the absence of Native and
60fps Interpolation rows remains static-only and is not visually verified in the actual menu.

### S006 — measured widescreen owners

C012/I007 and `tools/verify_projection.py` identify the complete six-writer CR24/CR25/CR26 census,
the view-dimension and projection-centre chain, focal-length owner, both display presets, stage
visibility angles, and rendering-path right-edge comparisons on the hashed executable.

Gap: Framework issue 0009 still misdecodes Tekken's GP1 368-pixel mode, and the measured owners have
not been driven in a completed frame or A/B-tested against a faithful 4:3 image. Issue 0008 tracks
the coordinated culling/coverage work.

### S007 — true widescreen output

Missing capability: no completed Tekken frame has demonstrated wider guest geometry, stage/effect
coverage, and final presentation while preserving vertical framing and the faithful 4:3 control.

### S008 — frames, input, audio, and gameplay

Missing capability: the product has not completed and visually presented a frame, accepted verified
gameplay input, produced verified title audio, or sustained gameplay.

### S009 — default playable widescreen product

Missing capability: `./run.sh` builds and launches the intended product, but that product does not yet
satisfy the observable frame, gameplay, or widescreen conditions of S007 and S008.
