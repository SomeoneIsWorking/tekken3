# Tekken 3 project state

This is the factual capability inventory. Epic intent lives in `docs/project-goals.md`, atomic work
in `docs/issues/`, ownership and placement in `docs/codemap.md`, and ordered reverse-engineering
dependencies in `docs/re-frontier.md`.

| ID | Capability / observable outcome | State | Dependencies | Goals |
|---|---|---|---|---|
| S001 | The selected USA disc executable is reproducibly identified and provisioned | verified | — | G001, G003 |
| S002 | Retail entry and direct-main startup execute deterministically to an independent boundary | verified | S001 | G001, G003 |
| S003 | The authenticated executable runs through the native/Lightrec gameplay product | partial | S001, S002 | G001, G003 |
| S004 | Boot and CD initialization are compared across independent or distinct execution engines | partial | S002 | G001, G003 |
| S005 | The title declares a non-temporal, guest-rendered widescreen capability contract | partial | S003 | G002 |
| S006 | Tekken-owned projection, display, visibility, and clipping state is identified for widescreen | partial | S001 | G002 |
| S007 | True widescreen renders additional correctly projected content | missing | S004, S005, S006 | G002 |
| S008 | Product frames, input, audio, and gameplay execute correctly | partial | S003, S004 | G001 |
| S009 | The default launcher delivers the playable widescreen product | missing | S007, S008 | G001, G002, G003 |
| S010 | Asset-free hosted verification builds and checks the real supported host product boundary | verified | S003 | G001, G003 |

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
`eb5f23a8b3506f8853b3cfadcedc024cd90818a0`; CI checks out Lightrec
`b1457137c31cedff5f440d59da29401d021ba2da`. It contains no disc, executable, BIOS, or runtime
translation cache and therefore claims no gameplay evidence. The same canonical Python gate passes
locally and in the hosted run recorded in S010.

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

Evidence: player composition installs `Tekken3Runtime`, loads the identity-checked executable as
runtime data, binds framework devices, installs image-and-address-keyed native overrides, and
dispatches the retail entry through psxport's per-Core Lightrec executor. The title resumes its
first synchronous 127-resource mode call over bounded host fields without changing the field budget.
An authenticated, headless seven-field run (issue 0011, PID `751763`, exit 0) reached the outer guest
return after six suspensions, completed the first frame, and reported 360,083 executed blocks,
2,235,207 executed instructions, and zero fallback. A synthetic nested-call control verifies the
original outer return address survives a changed live `r31`.

Gap: the product has not reached `NAMCO PRESENTS`, the menu, or representative gameplay. Historical
product evidence remains useful only as the measured native/device frontier because it predates this executor:
the isolated `3c342ec3` product PID `3216829` dispatched the retail entry, opened the real CHD, and
passed the synchronous directory-read and GetTN/GetTD owners. It then reached ResetGraph and trapped
the next protected guest VSync query in linked GPU timeout armer `FUN_8007E8F0`. Its exact PID exited
and is confirmed gone. The resulting native-ledger GPU arm/poll owner is combined-gate green but not
yet product-verified. A later 1,200-frame windowless run against the real CHD produced a presented
sink image and the `NAMCO PRESENTS` title card, but no menu or gameplay scene is covered. The next
product evidence must pass the 1,200-field Namco discriminator and subsequent gameplay gate.

### S004 — differential boot and CD initialization

Historical psxport-interpreter and independent-Mednafen runs agreed on 35/35 CPU fields at the
entry-to-main boundary. Those observations remain useful measurements, but the interpreter probe and
retired execution harness are deleted and are not current verification paths.

Gap: The independent CPU now continues through DPCR and the measured context-save path, but cannot yet
execute B(19) HookEntryInt and return for another two-engine comparison. Whole-product execution now
passes CD/TOC initialization with no guest VSync call and reaches ResetGraph. Issue 0011 records the
exact GPU timeout-arm chain and the combined-gate-green native field/poll owner for
`FUN_8007E8F0/FUN_8007E924`. The newer Lightrec run covers one frame, but no gameplay.

### S005 — title render-capability contract

`Tekken3Runtime::renderCapabilities()` returns the shared `widescreenOnly()` policy. The runtime seam
checks GTE as the only player-selectable path, PSX as a supported diagnostic path, Native as
unsupported, and temporal interpolation as unsupported.

Evidence: The historical shared capability implementation was recorded at `psxport.pin` `fb08d30f`. The exact
Clang gate passes CTest 17/17, clang-tidy 19/19, and the 13/13 capability seam. A bounded product run
also rejected a persisted `native` selection as unsupported and resolved it to GTE.

Gap: The new headless product run completed a first present, but the absence of Native and 60fps
Interpolation rows is verified only at the source contract and not visually in the actual menu.

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
4:3 image. A historical runner presented the title-loader card; the current Lightrec run completed
one frame without image inspection. The separate 600/780 stage-tile visibility wedge remains
measurement-dependent: a real wide
frame must show whether it requires a derived frustum adjustment.

### S007 — true widescreen output

Missing capability: no completed Tekken frame has demonstrated wider guest geometry, stage/effect
coverage, and final presentation while preserving vertical framing and the faithful 4:3 control.

### S008 — frames, input, audio, and gameplay

Evidence: the bounded headless product run completed seven host fields and one title frame, including
per-field presentation/audio/pad service during the suspended guest call (issue 0011). Gap: the
resulting image was not inspected, and verified gameplay input, title audio, and sustained gameplay
remain absent.

### S009 — default playable widescreen product

Missing capability: `./run.sh` builds and launches the intended product, but that product does not yet
satisfy the observable frame, gameplay, or widescreen conditions of S007 and S008. Launcher and direct
product `-h/--help` contracts both exit zero before dependency, runtime, or disc discovery.

### S010 — asset-free hosted verification

The Linux workflow and `tools/verify.py` own one reproducible asset-free gate over the shipping
product boundary, title contracts, formatting, lint, and linked execution policy.
Evidence: the Linux x86_64 asset-free product composition gate passed on main commit
`3afb4cf0fa167cf197dd6056cf00d5cfaeaa63d1` in
[run 33960101763](https://github.com/SomeoneIsWorking/tekken3/actions/runs/33960101763).
This verifies composition only; gameplay and unsupported host gaps remain as recorded above.
