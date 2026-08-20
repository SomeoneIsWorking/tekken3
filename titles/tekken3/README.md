# Tekken 3

## Measured target

The selected target is the supplied USA disc image (NTSC-U/C). Its `SYSTEM.CNF` names
`cdrom:\TEKKEN3\SLUS_004.02;1`, and the disc directory places that executable at LBA 25.

| Field | Measured value |
|---|---|
| Executable | `TEKKEN3/SLUS_004.02` |
| Disc extent | LBA 25, 1,185,792 bytes |
| SHA-256 (complete PS-X EXE) | `fbda8b68e5799dbef4af39a161783bc670c15b0aa0e87dce65e210717da19b8c` |
| Entry (`pc0`) | `0x80079C70` |
| Load address (`t_addr`) | `0x80010000` |
| Text size (`t_size`) | `0x00121000` bytes |
| Text extent | `[0x80010000, 0x80131000)` |
| Header stack | `0x801FFFF0` |

The startup body zeroes BSS `[0x8009B9A8, 0x800B0548)`, derives GP `0x8009B9A8`, stack top
`0x801FFFF8`, heap base `0x800B0548`, and heap size `0x00147AB0`, then stores the heap size/base
through `0x80098A6C` and `0x80098A68`. Ghidra decompilation and a post-decompile instruction
spot-check agree that the JAL at `0x80079D04` targets `0x80028BA0` with a `nop` delay slot.

That target is Tekken 3's non-returning main loop, not a libc initializer. `crt0_extract` labels the
first startup JAL `libcInit` generically and explicitly reports that this target is not the A(39h)
InitHeap thunk. The structural constants above are measured evidence for a future game seam; none is
wired into shipping code.

## Reproduce the identity measurement

After the root README's Clang configure, set `TEKKEN3_DISC` to the untracked CHD, then run:

```sh
CCACHE_DISABLE=1 cmake --build build --target discdump crt0_extract
build/psxport_build/tools/discdump list "$TEKKEN3_DISC"
build/psxport_build/tools/discdump get SYSTEM.CNF "$TEKKEN3_DISC" scratch/raw/tekken3
build/psxport_build/tools/discdump get TEKKEN3/SLUS_004.02 "$TEKKEN3_DISC" scratch/raw/tekken3
sha256sum scratch/raw/tekken3/SLUS_004.02
build/psxport_build/tools/crt0_extract scratch/raw/tekken3/SLUS_004.02
```

No disc-derived file belongs in git. This measurement does not establish that a Tekken 3 port boots
or that a recompiled substrate exists.
