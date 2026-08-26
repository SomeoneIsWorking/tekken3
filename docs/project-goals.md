# Tekken 3 project goals

## G001 — Faithful playable PC port

Build a PC product from the selected USA Tekken 3 executable and user-supplied disc content. The
default launcher must boot the real game, render its frames, accept input, produce audio, and sustain
gameplay. Independent reference execution must cover the behavioral boundaries used as evidence;
compilation, isolated function tests, or a framework smoke target do not satisfy this goal.

Success conditions:

- `./run.sh` provisions the required user assets, derives the generated substrate, and launches the
  intended Tekken 3 product without maintainer-only RE tools.
- The product reaches and sustains visible gameplay with working input and audio.
- Faithful behavior is compared against independent retail execution at deterministic boundaries,
  with every known divergence recorded rather than hidden by a fallback.

Constraints and non-goals:

- Generated code is derived from verified user-supplied executable bytes and is never hand-edited or
  committed.
- Disc images and extracted game files remain outside git.
- A test executable, boot probe, or psxport smoke binary is not the product.

## G002 — True widescreen through Tekken-owned projection state

Extend Tekken 3's measured guest view, projection, visibility, primitive coverage, and final
presentation to wide aspect ratios while preserving the faithful 4:3 path.

Success conditions:

- Wider modes reveal correctly projected horizontal content without stretching, cropping, or
  changing vertical framing.
- Guest geometry, stage/effect visibility, draw coverage, and final sampling widen together.
- The original 4:3 mode remains behaviorally and visually identical to its faithful baseline.

Constraints and non-goals:

- Tekken 3 is a non-lerp target. It exposes no 60fps/interpolation option and owns no temporal state
  solely for interpolation.
- It exposes no native-renderer option and does not gain a title-owned native renderer, native
  producer, or native-depth path.
- GTE, ordering-table, and GP0 output may be diagnostic evidence but are not reconstructed into an
  authored replacement picture.

## G003 — Reproducible evidence and player setup

Keep executable identity, generated-code derivation, framework provenance, and verification
reproducible from a fresh clone with the documented native dependencies, `uv`, a compatible C/C++
compiler, and user-supplied game assets.

Success conditions:

- Executable selection and extraction refuse incorrect regional or mutated inputs by measured
  identity.
- One frozen Python environment drives provisioning, generation, configuration, build, and checks.
- The recorded psxport pin names the exact framework revision used for product evidence.
- Maintainer-only tools such as Ghidra are unnecessary for a player build.
