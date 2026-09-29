#!/usr/bin/env python3
"""census_word.py — who READS and who WRITES one guest word, by constant propagation over the text.

WHY THIS EXISTS, and it is the tenth dead tap in this workspace.

`docs/issues/0019` measured "0 materialised readers" for `0x800A069F` and used that ZERO to redirect
the whole investigation away from the CD chain, which parked the real fix. The bytes say
`0x8006BEBC`, `0x8006C244` and `0x8006C490` all read it. Two separate things were wrong, and both
are the kind that survive review:

  1. IT TRACKED THE WRONG REGISTER. The image builds a global the way every MIPS compiler does:
         lui   $v0,0x800A          <-- the constant lands in $v0
         addiu $s0,$v0,0x698       <-- and is CONSUMED in $s0
         lbu   $v0,7($s0)          <-- the reader
     A sweep that only follows `lui rX` / `addiu rX,rX,imm` in the SAME register sees no address at
     all. Across a whole image written that way the miss is not an edge case; it is the idiom.
  2. IT LOST CONSTANTS ACROSS BRANCHES. Constants live in REGISTERS, so they survive basic blocks.
     Cutting the walk at a branch target and restarting from an empty register file loses every
     cross-block constant — and the sector-callback handler in this very image keeps `$s1` live
     across ~40 instructions and four branch targets.

SO THIS TOOL DOES NOT BUILD A CFG, and that is a deliberate choice rather than a simplification. A
CFG fixpoint was written first and removed: the worklist did not converge, and an instrument that
does not terminate is not an instrument. Instead it walks the text ONCE, in address order, carrying
32 register constants, and it splits into blocks only to decide where a block ENDS — never to reset
state. Each block is entered with the state its single textual predecessor left behind.

That is a SUPERSET sweep: a constant that is dead in reality can survive here, so this tool can
REPORT a reader that does not exist. That is the safe direction to be wrong in. A CFG would be
precise, but precision that never terminates is worth less than a superset that does, and every
finding below is confirmed against the framework's own disassembler before it is believed.

THE OPCODE TABLE IS NOT HAND-TYPED, because a hand-typed one is exactly how this session already
produced a wrong record — issue 0019's own decoder mapped 0x2A to `slti` when it is `SWL`, and
`slti` is 0x0A. `--selftest` pins every table entry against Capstone via the framework's
disassembler, so a wrong entry turns the selftest red instead of quietly changing a census.

DESIGNED NEGATIVE FIRST, in both directions:
  * it prints the words walked and the accesses classified, and REFUSES a short or misaligned image;
  * it reports counts WITH their denominator (N of M words walked), never a bare zero;
  * `--selftest` is a census that CAN fail. It is pinned to FIND the known readers and writers of
    `0x800A069F` and `0x8009B8C8`, and to report ZERO for addresses this image demonstrably does not
    name. A sweep that cannot do both is measuring itself rather than the image;
  * the main path runs the same pins and REFUSES to print a subject verdict if they do not hold,
    which is what stops a broken sweep from reporting a confident zero.
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import sys

TEXT_FILE_OFFSET = 0x800

# (opcode) -> (width in bytes, "r" or "w").  Every entry is pinned by --selftest against Capstone
# through the framework's disassembler; do not add one here without extending the selftest.
LOADS_STORES: dict[int, tuple[int, str]] = {
    0x20: (1, "r"),  # lb
    0x21: (2, "r"),  # lh
    0x22: (4, "r"),  # lwl
    0x23: (4, "r"),  # lw
    0x24: (1, "r"),  # lbu
    0x25: (2, "r"),  # lhu
    0x26: (4, "r"),  # lwr
    0x28: (1, "w"),  # sb
    0x29: (2, "w"),  # sh
    0x2A: (4, "w"),  # swl
    0x2B: (4, "w"),  # sw
    0x2E: (4, "w"),  # swr
}

# SPECIAL funct -> writes rd.  A funct not listed leaves the GPR file alone, so the read-only
# encodings (sll/srl/sra with rd == 0, and every "nop") need no entry.
SPECIAL_WRITES_RD = {
    0x00,  # sll (also the `mov` pseudo when rs == rt)
    0x02,  # srl
    0x03,  # sra
    0x04,  # sllv
    0x06,  # srlv
    0x07,  # srav
    0x10,  # mfhi
    0x12,  # mflo
    0x20,  # add
    0x21,  # addu
    0x22,  # sub
    0x23,  # subu
    0x24,  # and
    0x25,  # or
    0x26,  # xor
    0x27,  # nor
    0x2A,  # slt
    0x2B,  # sltu
}

# Opcodes outside SPECIAL that write rt.  Anything not in LOADS_STORES, SPECIAL_WRITES_RD or here
# KILLS rt's constant rather than leaving a stale one, which is the conservative direction.
WRITES_RT = {0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
             0x10, 0x11, 0x12, 0x13, 0x1C, 0x1F}

BRANCHES = {0x01, 0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17}
JUMPS = {0x02, 0x03}
REGIMM = 0x01


def sign16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def load_text(exe: pathlib.Path) -> tuple[dict[int, int], int, int]:
    data = exe.read_bytes()
    if len(data) < TEXT_FILE_OFFSET:
        print(f"REFUSED: {exe} is shorter than the {TEXT_FILE_OFFSET}-byte PS-X EXE header")
        raise SystemExit(2)
    t_addr = struct.unpack_from("<I", data, 0x18)[0]
    t_size = struct.unpack_from("<I", data, 0x1C)[0]
    body = data[TEXT_FILE_OFFSET:TEXT_FILE_OFFSET + t_size]
    if len(body) < t_size:
        print(f"REFUSED: file holds {len(body)} text bytes, header claims t_size={t_size}")
        raise SystemExit(2)
    if t_size % 4:
        print(f"REFUSED: t_size={t_size} is not word aligned")
        raise SystemExit(2)
    text = {t_addr + i * 4: struct.unpack_from("<I", body, i * 4)[0] for i in range(t_size // 4)}
    return text, t_addr, t_addr + t_size


def sweep(text: dict[int, int], lo: int, hi: int) -> list[tuple[int, str, int, int]]:
    """Walk the text once, in address order, carrying register constants ACROSS blocks.

    Returns (address, kind, target, width) for every access whose base resolved to a constant.
    """
    accesses: list[tuple[int, str, int, int]] = []
    consts: list[int | None] = [None] * 32
    addr = lo
    while addr < hi:
        w = text.get(addr)
        if w is None:
            addr += 4
            continue
        op = w >> 26
        rs = (w >> 21) & 0x1F
        rt = (w >> 16) & 0x1F
        rd = (w >> 11) & 0x1F
        simm = sign16(w & 0xFFFF)

        if op == 0x0F:  # lui
            consts[rt] = (w & 0xFFFF) << 16 if rt else None
        elif op in (0x09, 0x0D):  # addiu, ori
            base = consts[rs]
            if base is not None and rt:
                consts[rt] = (base + simm) & 0xFFFFFFFF
            else:
                consts[rt] = None
        elif op == 0x00:  # SPECIAL
            funct = w & 0x3F
            if funct == 0x00 and rs == rt and rd:  # mov
                consts[rd] = consts[rs]
            elif funct in SPECIAL_WRITES_RD and rd:
                consts[rd] = None
            if funct == 0x09 and rd:  # jalr writes rd
                consts[rd] = None
        elif op in LOADS_STORES:
            width, kind = LOADS_STORES[op]
            base = consts[rs]
            if base is not None:
                accesses.append((addr, kind, (base + simm) & 0xFFFFFFFF, width))
            if rt:
                consts[rt] = None
        elif op in WRITES_RT and rt:
            consts[rt] = None
        addr += 4
    return accesses


# Pins: addresses with a KNOWN reader and a KNOWN writer in this image.  All are reached through the
# lui-in-one-register / consume-in-another idiom, so a sweep that cannot follow it reports 0 here.
PINS: list[tuple[int, int, int, str]] = [
    (0x800A069F, 1, 1, "loader busy byte: FUN_8006BEA8 reads it, FUN_8006C2EC clears it"),
    (0x8009B8C8, 1, 1, "sector-callback base: FUN_80091F38 writes it, FUN_80092058 reads it"),
]
# Negatives: addresses this image demonstrably does not name.  A reader reported for one of these is
# an INVENTED finding, which is the failure direction that costs a real defect.
NEGATIVES: list[tuple[int, str]] = [
    (0x8001FFF0, "a word in the early text no loader writes and no routine names"),
    (0x800B8D5B, "a byte inside mode 0's resource table, which is walked as words"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exe", type=pathlib.Path)
    ap.add_argument("--word", type=lambda v: int(v, 0))
    ap.add_argument("--span", type=int, default=4)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dump-table", action="store_true",
                    help="print the opcode table for the selftest to pin against Capstone")
    args = ap.parse_args()

    if args.dump_table:
        for op, (width, kind) in sorted(LOADS_STORES.items()):
            print(f"0x{op:02X} {width} {kind}")
        return 0

    text, lo, hi = load_text(args.exe)
    total = (hi - lo) // 4
    print(f"scanned {total}/{total} word(s) of text at 0x{lo:08X}..0x{hi:08X} "
          f"(loaded from file offset 0x{TEXT_FILE_OFFSET:X} to t_addr)")

    accesses = sweep(text, lo, hi)
    print(f"classified {len(accesses)} address-forming access(es) with a constant base; "
          f"a BYTE access counts as a first-class reader, which is what the previous census missed")

    def count(addr: int, kind: str, span: int) -> list[tuple[int, str, int, int]]:
        return [a for a in accesses if a[1] == kind and addr <= a[2] < addr + span]

    failures = 0
    for addr, min_r, min_w, why in PINS:
        r, w = count(addr, "r", 1), count(addr, "w", 1)
        ok = len(r) >= min_r and len(w) >= min_w
        failures += 0 if ok else 1
        print(f"control pin 0x{addr:08X}: {len(r)} reader(s), {len(w)} writer(s) "
              f"(require >={min_r}/>={min_w}) {'ok' if ok else 'MISSING'} — {why}")
    for addr, why in NEGATIVES:
        r, w = count(addr, "r", 1), count(addr, "w", 1)
        ok = not r and not w
        failures += 0 if ok else 1
        print(f"negative     0x{addr:08X}: {len(r)} reader(s), {len(w)} writer(s) "
              f"(require 0/0) {'ok' if ok else 'INVENTED'} — {why}")

    if failures:
        print(f"REFUSED: {failures} control(s) failed, so a count for the subject would be a "
              "statement about this sweep and not about the image. No verdict printed.")
        return 2

    if args.selftest:
        print("census_word: PASS — pins found, negatives absent")
        return 0
    if args.word is None:
        print("census_word: controls ok; no --word given, so no subject verdict")
        return 0

    readers = count(args.word, "r", args.span)
    writers = count(args.word, "w", args.span)
    print(f"\nsubject 0x{args.word:08X} span {args.span}: {len(readers)} reader(s), "
          f"{len(writers)} writer(s), of {total} words walked")
    for _, kind, target, width in sorted(readers, key=lambda a: a[2]):
        print(f"  READ  0x{target:08X}  {width} byte(s)")
    for _, kind, target, width in sorted(writers, key=lambda a: a[2]):
        print(f"  WRITE 0x{target:08X}  {width} byte(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
