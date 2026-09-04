# Tekken 3 project state

This is the factual capability inventory. Epic intent lives in `docs/project-goals.md`, atomic work
in `docs/issues/`, ownership and placement in `docs/codemap.md`, and ordered reverse-engineering
dependencies in `docs/re-frontier.md`.

| ID | Capability / observable outcome | State | Dependencies | Goals |
|---|---|---|---|---|
| S001 | The selected USA disc executable is reproducibly identified and provisioned | verified | — | G001, G003 |
| S002 | Retail entry and direct-main startup execute deterministically to an independent boundary | verified | S001 | G001, G003 |
| S003 | The authenticated executable runs through the native/Lightrec gameplay product | missing | S001, S002 | G001, G003 |
| S004 | Boot and CD initialization are compared across independent or distinct execution engines | partial | S002 | G001, G003 |
| S005 | The title declares a non-temporal, guest-rendered widescreen capability contract | partial | S003 | G002 |
| S006 | Tekken-owned projection, display, visibility, and clipping state is identified for widescreen | partial | S001 | G002 |
| S007 | True widescreen renders additional correctly projected content | missing | S004, S005, S006 | G002 |
| S008 | Product frames, input, audio, and gameplay execute correctly | missing | S003, S004 | G001 |
| S009 | The default launcher delivers the playable widescreen product | missing | S007, S008 | G001, G002, G003 |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | partial | S003 | G001, G003 |

## Current focus

S003 is the current focus. The first discriminator is the native/Lightrec product reaching `NAMCO
PRESENTS` within 1,200 frames while executing nonzero Lightrec blocks and routing all 14
address-based original calls through the shipping dispatcher. Product inspection must prove that
Lightrec remains the default and no interpreter gameplay selector exists; runtime evidence must
report every bounded JIT-refusal fallback and satisfy its release threshold. That checkpoint is
followed by a representative interactive gameplay run.

## Hosted verification and host gaps

Linux x86_64 is the only currently supported host product boundary. The tracked GitHub Actions job
uses full history, disables persisted credentials and caches, installs pinned Python tooling, builds
the actual asset-free `tekken3_port`, runs every asset-free title contract plus clang-format and
clang-tidy, and inspects the linked execution boundary. The consumer pins PSXPort
`639e3630af3af9ed519bffa7da53c229c689b4d1`; CI checks out Lightrec
`b764c4c9f4bc425a56bfc4c32333ff8200ce8ab9`. It contains no disc, executable, BIOS, or runtime
translation cache and therefore claims no gameplay evidence. The same canonical Python gate passes
locally; the first hosted run remains pending.

Windows x86_64 is an applicable future PC host but currently unsupported: psxport still exports GNU
linker `--wrap` options and has no MSVC/clang-cl product contract. macOS arm64 is likewise unsupported
while that GNU linker contract remains and no AppleClang package/runtime gate exists. Android arm64
is unsupported because this title has no Activity/JNI/package owner and does not yet consume the
shared Android build contract. Successful no-op jobs for those platforms would be false evidence, so
they remain explicit gaps rather than green matrix entries.

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

### S003 — native/Lightrec gameplay product

Missing capability: player composition must install `Tekken3Runtime`, load the identity-checked executable as runtime
data, binds framework devices, installs image-and-address-keyed native overrides, and dispatches the
retail entry through psxport's per-Core Lightrec executor. Lightrec owns translated-code memory and
its cache. psxport owns CPU/machine synchronization, HLE/device callbacks, bounded executor exits,
override-aware original calls, and executable-memory invalidation.

Current gap: the target is wired to psxport's per-Core Lightrec execution boundary, including shared
per-reason fallback telemetry and the bounded fallback threshold. Historical product evidence remains
useful only as the measured native/device frontier because it predates this executor:
the isolated `3c342ec3` product PID `3216829` dispatched the retail entry, opened the real CHD, and
passed the synchronous directory-read and GetTN/GetTD owners. It then reached ResetGraph and trapped
the next protected guest VSync query in linked GPU timeout armer `FUN_8007E8F0`. Its exact PID exited
and is confirmed gone. The resulting native-ledger GPU arm/poll owner is combined-gate green but not
yet product-verified. A later 1,200-frame windowless run against the real CHD produced a presented
sink image and the `NAMCO PRESENTS` title card, but no menu or gameplay scene is covered. The next
product evidence must come from nonzero Lightrec execution through the shipping boundary and must
include the executor's complete fallback report with a passing threshold.

### S004 — differential boot and CD initialization

Historical psxport-interpreter and independent-Mednafen runs agreed on 35/35 CPU fields at the
entry-to-main boundary. Those observations remain useful measurements, but the interpreter probe and
retired execution harness are deleted and are not current verification paths.

Gap: The independent CPU now continues through DPCR and the measured context-save path, but cannot yet
execute B(19) HookEntryInt and return for another two-engine comparison. Whole-product execution now
passes CD/TOC initialization with no guest VSync call and reaches ResetGraph. Issue 0011 records the
exact GPU timeout-arm chain and the combined-gate-green native field/poll owner for
`FUN_8007E8F0/FUN_8007E924`. No frame or gameplay is covered.

### S005 — title render-capability contract

`Tekken3Runtime::renderCapabilities()` returns the shared `widescreenOnly()` policy. The runtime seam
checks GTE as the only player-selectable path, PSX as a supported diagnostic path, Native as
unsupported, and temporal interpolation as unsupported.

Evidence: The historical shared capability implementation was recorded at `psxport.pin` `fb08d30f`. The exact
Clang gate passes CTest 17/17, clang-tidy 19/19, and the 13/13 capability seam. A bounded product run
also rejected a persisted `native` selection as unsupported and resolved it to GTE.

Gap: The product did not reach a first present or create an X11 window, so the absence of Native and
60fps Interpolation rows is verified only at the source contract and not visually in the actual menu.

### S006 — measured widescreen owners

C012/I007 and `tools/verify_projection.py` identify the complete six-writer CR24/CR25/CR26 census,
the view-dimension and projection-centre chain, focal-length owner, both display presets, stage
visibility angles, and rendering-path right-edge comparisons on the hashed executable.

Framework commit `2e840231` now decodes Tekken's GP1 368-pixel mode generically. The title's
`Tekken3Widescreen` owner binds the measured 384x480-view/368-draw and 320x240/320 facts to the shared
projection plan, then uses the same resolved guest draw width for the stage/effect primitive
clippers while retaining their original 4:3 guest bodies. The hermetic contract proves the wide
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

### S010 — asset-free hosted verification

The Linux workflow and `tools/verify.py` own one reproducible asset-free gate over the shipping
product boundary, title contracts, formatting, lint, and linked execution policy. The remaining gap
is a successful hosted run of the landed workflow; unsupported host products are recorded above.
