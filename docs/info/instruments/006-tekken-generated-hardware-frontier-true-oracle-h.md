---
id: I006
kind: instrument
status: trusted
created: 2026-08-22
---

## Instrument

Tekken generated hardware-frontier true-oracle harness

## Validated by

On the real USA executable, tools/recomp_boundary.py compared psxport shipping-emitter execution with independent Mednafen at four CPU boundaries through post-store 0x80085D98. The separate vendored-Mednafen IRQ target proves it can expose a non-zero asserted state before producing Tekken's zero reset, then agrees with the generated path on 3/3 device observations at 0x80085DA4. The suite reports a forced a0 disagreement, rejects altered generated source, rejects a missing edge, rejects the wrong hardware register, and refuses an unmeasured runner target (SELFTEST 9/9; IRQ SELFTEST 2/2).

## Known failure modes

The standalone CPU oracle deliberately stops on every hardware access, so it cannot provide CPU-register ground truth after 0x80085D98. Device semantics are compared independently, but continuing the CPU requires a framework oracle model that resumes the same Mednafen CPU after modeled I/O.
