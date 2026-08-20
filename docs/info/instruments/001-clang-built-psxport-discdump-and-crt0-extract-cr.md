---
id: I001
kind: instrument
status: trusted
created: 2026-08-20
---

## Instrument

Clang-built psxport discdump and crt0_extract, cross-checked with Ghidra for Tekken 3 target identity and startup measurement

## Validated by

crt0_extract selftest exercised 59 checks over valid and negative shapes; discdump listed 7 files/directories, extracted both selected files at declared sizes, and rejected a deliberately absent filename. Ghidra decompiled the entry and first jal target, while a narrow post-decompile disassembly confirmed the exact BSS loop, heap stores, gp setup, jal target, and nop delay slot.

## Known failure modes

`discdump` establishes the filesystem identity of the supplied image, not whether that image is the intended retail revision. `crt0_extract` stops at the first startup JAL and names that field `libcInit`; on this executable the target is the game main loop, so only the decoded address and structural startup fields are evidence. The framework's `crossvalidate_crt0.py` assumes that startup reaches an out-of-image BIOS boundary and refused after 400,000 executed instructions here, comparing zero fields. Ghidra imported a raw RAM image, had to create the requested entry/target functions explicitly, and reported a p-code error at `0x800DB1B8` outside the startup functions used by C001; its output is corroboration for those requested functions, not a complete program model.

The framework's `tools/disasm.py` accepts a raw 2 MiB RAM dump and does not validate that input
shape. Passing the PS-X EXE directly makes its address mask ignore the 0x800-byte executable header,
so it confidently disassembles the wrong bytes. Use the loaded RAM image or a PS-X EXE-aware reader.
