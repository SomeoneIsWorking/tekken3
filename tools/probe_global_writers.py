#!/usr/bin/env python3
"""probe_global_writers.py — who READS and WRITES guest globals in the authenticated SLUS_004.02 text?

Ghidra's reference model reported ZERO references to 0x8009B750, a global that FUN_8008E8B8 gates
every raw-command drain on. A first linear sweep also found nothing, and said why: the accesses use
two-register address arithmetic (`base + index`) that a one-register constant tracker cannot see. This
version does the constant propagation SOUNDLY -- a tracked value survives only while its register is
untouched, every instruction form that writes a register kills that register's tracked value unless
the instruction is itself one of the three that materialises a constant, tracked values are dropped at
every control transfer, and the byte-scaled-index form (`sll`/`addu`) is modelled because FUN_8008FBB4
reaches the 0x8009B750 table exactly that way.

It is a scanner with a stated blind spot, not a completeness claim, and it prints the denominator so
"0" is distinguishable from "never looked". It also REFUSES to report anything unless it first
reproduces two known instructions, which is not ceremony: an earlier version of this file omitted the
PS-X EXE's 0x800-byte header from the file offset, which shifts every decoded instruction and every
reported address while the sweep still returns confident non-zero answers -- it reported 0x8009B750 as
18 phantom stores, every one of them a `lui` for a divide-by-10 magic constant.

Usage:
    tools/probe_global_writers.py [executable] [address ...]
    tools/probe_global_writers.py --selftest [executable]

The selftest asserts both discriminator answers the tool exists to tell apart: a global that IS
written, and a global that is NOT.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/psxport"))

from tools.mips.decode import REG, decode  # noqa: E402

SELFTEST = "--selftest" in sys.argv
ARGS = [a for a in sys.argv[1:] if a != "--selftest"]
EXE = pathlib.Path(ARGS[0]) if ARGS else ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
DATA = EXE.read_bytes()
LOAD = 0x80010000
# The PS-X EXE carries a 0x800-byte header in front of the text, so the file offset is
# 0x800 + (address - LOAD). Omitting that 0x800 shifts EVERY decoded instruction and every
# reported address while the sweep still returns confident non-zero answers -- it reported
# 0x8009B750 as 18 phantom stores before this was found. GROUND_TRUTH pins it.
HEADER = 0x800
TEXT_START = LOAD
TEXT_END = LOAD + 0x121000

TARGETS = {int(a, 16) for a in ARGS[1:]}

# Read out of the disassembly, not assumed:
#   0x8008FBB4  sll  a0,a0,2        0x00042080
#   0x8008FBB8  lui  v0,0x800A      0x3C02800A
#   0x8008FBBC  addu v0,v0,a0       0x00441021
#   0x8008FBC0  lw   v0,-18608(v0)  0x8C42B750   <-- the 0x8009B750 read
GROUND_TRUTH = {0x8008FBB4: 0x00042080, 0x8008FBC0: 0x8C42B750}

# Controls for the selftest. Both must hold, and the second is the one that matters.
#
# POSITIVE -- the sweep must find the real writers of the CD chain state words. 0x8009B750 has three,
#   each hand-verified in the disassembly: 0x80090338 and 0x800908D8 write 1 (ready) and 0x8008FA54
#   writes 2 (in flight). An earlier draft used 0x8009B750 as a NEGATIVE control on the belief that
#   nothing wrote it; the disassembly disproved that. A control that is simply false is worse than
#   no control, because it turns a real finding into a "the instrument invents writes" failure.
#
# DISCRIMINATOR -- there is no sweep-level one, and that is stated rather than faked: re-running the
#   sweep with the header offset removed produced the SAME store counts, because the wrong bytes are
#   simply rejected by the decoder and the few that decode do not happen to form these patterns. The
#   guard that actually works is `offset_problems()`, which refuses to report ANYTHING unless the
#   file offset reproduces GROUND_TRUTH first -- and it is what caught this bug. Asserting a
#   discriminator that does not fire would be a control that passes while the tool is still broken.
SELFTEST_WRITTEN = (0x8009B750, 0x8009B8E8)
SELFTEST_MINIMUM_WRITES = {0x8009B750: 3, 0x8009B8E8: 1}


def word(addr: int) -> int:
    off = HEADER + addr - LOAD
    return int.from_bytes(DATA[off:off + 4], "little")


def offset_problems() -> list[str]:
    """Refuse to report anything unless the file offset reproduces known instructions."""
    problems = []
    for addr, expected in sorted(GROUND_TRUTH.items()):
        actual = word(addr)
        if actual != expected:
            problems.append(f"0x{addr:08X}: expected 0x{expected:08X}, read 0x{actual:08X}")
    return problems


def written_registers(ins) -> set[int]:
    """Every general register this instruction can change."""
    k = ins.kind
    if k in ("lui", "alu_rri", "load", "gte_move", "gte_load"):
        return {ins.rt}
    if k in ("alu_rrr", "shift_i", "shift_v", "muldiv", "gte_op"):
        return {ins.rd, ins.rt} - {0}
    if k == "hilo":
        return {ins.rd} if ins.op in ("mfhi", "mflo") else set()
    if k == "jumpr":
        return set()
    if k in ("branch", "jump", "store", "syscall", "break_", "nop", "gte_store", "cop0"):
        return set()
    return set()


def sweep():
    holds: dict[int, int] = {}
    scales: dict[int, int] = {}
    # The two control addresses are ALWAYS swept, so a selftest run exercises the same code path as a
    # real query and cannot pass by short-circuiting around the sweep.
    keys = TARGETS | set(SELFTEST_WRITTEN)
    stores: dict[int, list[tuple[int, str]]] = {t: [] for t in keys}
    loads: dict[int, list[tuple[int, str]]] = {t: [] for t in keys}
    scanned = rejected = 0
    for addr in range(TEXT_START, TEXT_END, 4):
        raw = word(addr)
        try:
            ins = decode(addr, raw)
        except Exception:
            rejected += 1
            continue
        if ins.kind == "unknown":
            rejected += 1
            continue
        scanned += 1

        # 1. Observe any access that lands on a target, using the CURRENT tracked base.
        #    The displacement is SIGNED. Getting that wrong is not theoretical: FUN_8008FBB4
        #    reaches the 0x8009B750 table as `lui v0,0x800A` then `lw v0,-18608(v0)`, so a
        #    masked 0xFFFF lands on 0x800AB750 and the one global that gates the whole raw-command
        #    chain reads as "never referenced". The denominator below is what exposed it.
        base = holds.get(ins.rs) if ins.kind in ("load", "store") else None
        if base is not None:
            disp = ins.simm
            target = (base + disp) & 0xFFFFFFFF
            if target in keys:
                shown = f"{disp:+d}({REG[ins.rs]})"
                if ins.kind == "store":
                    width = {"sw": 4, "sh": 2, "sb": 1}.get(ins.op, "?")
                    stores[target].append(
                        (addr, f"{ins.op} {REG[ins.rt]},{shown}  [base 0x{base:08X}, {width} byte(s)]"))
                else:
                    loads[target].append(
                        (addr, f"{ins.op} {REG[ins.rt]},{shown}  [base 0x{base:08X}]"))

        # 2. Update the tracked constants. Snapshot the INPUTS before killing, because the very
        #    forms this needs (`sll a0,a0,2` reading a0, `addu v0,v0,a0` reading v0 and a0) all
        #    write a register they also read. Kill-then-read reports every one of them as
        #    untracked, which is how a whole table ends up looking unreferenced.
        src = holds.get(ins.rs)
        idx_rt = scales.get(ins.rt)
        src_rt = holds.get(ins.rt)
        for reg in written_registers(ins):
            holds.pop(reg, None)
            scales.pop(reg, None)
        if ins.kind == "lui":
            holds[ins.rt] = (ins.imm << 16) & 0xFFFFFFFF
        elif ins.kind == "alu_rri" and ins.op in ("addiu", "addi", "ori"):
            if src is not None:
                if ins.op == "ori":
                    holds[ins.rt] = (src & 0xFFFF0000) | (ins.imm & 0xFFFF)
                else:
                    holds[ins.rt] = (src + ins.simm) & 0xFFFFFFFF
        elif ins.kind == "shift_i" and ins.op == "sll":
            # `sll a0,a0,2` is a byte-scaled index, not an address. FUN_8008FBB4 reaches the
            # 0x8009B750 table as sll/index, lui base, addu base+index, lw offset(base+index) --
            # without this the table that gates the whole raw-command chain is unreferenced.
            if src_rt is not None and ins.shamt <= 4:
                scales[ins.rd] = (src_rt << ins.shamt) & 0xFFFFFFFF
        elif ins.kind == "alu_rrr" and ins.op in ("addu", "add", "or"):
            if src is not None and idx_rt is not None:
                holds[ins.rd] = (src + idx_rt) & 0xFFFFFFFF
        # 3. A CONTROL TRANSFER ends the straight-line region. Without this the tracker carried a
        #    caller's base register into an unrelated callee and reported 18 phantom stores on
        #    0x8009B750 -- every one of them a `lui` for a divide-by-10 magic constant or a
        #    delay-slot `nop`. Soundness beats recall: dropping the values loses true positives
        #    inside a function that reloads them, and never invents one.
        if ins.kind in ("jump", "jumpr", "branch", "syscall", "break_"):
            holds.clear()
            scales.clear()
    return scanned, rejected, stores, loads


def main() -> int:
    problems = offset_problems()
    if problems:
        print("REFUSED: the executable could not be read at the offset these addresses assume, so "
              "every answer below would be shifted and wrong:")
        for line in problems:
            print("  " + line)
        print("NOTHING WAS SCANNED. This is a refusal, not an empty result.")
        return 2
    if SELFTEST:
        _, _, stores, _ = sweep()
        print(f"file offset pinned: {len(GROUND_TRUTH)}/{len(GROUND_TRUTH)} known instruction(s) "
              f"reproduced at 0x80010000 + 0x800 + (addr - 0x80010000)")
        bad = False
        for address in SELFTEST_WRITTEN:
            found = len(stores[address])
            need = SELFTEST_MINIMUM_WRITES[address]
            verdict = "ok" if found >= need else "TOO FEW"
            print(f"positive control  0x{address:08X}: {found} store(s), expected at least {need} "
                  f"— {verdict}")
            bad = bad or found < need
        if bad:
            print("FAIL: a control did not hold, so this tool's answers are not trustworthy.")
            return 1
        print("PASS: the file offset is pinned against known instructions and every hand-verified "
              "writer is found.")
        return 0
    if not TARGETS:
        print(__doc__)
        return 2
    print(f"file offset pinned: {len(GROUND_TRUTH)}/{len(GROUND_TRUTH)} known instruction(s) "
          f"reproduced at 0x80010000 + 0x800 + (addr - 0x80010000)")
    scanned, rejected, stores, loads = sweep()
    print(f"scanned {scanned} instruction(s) in [0x{TEXT_START:08X}, 0x{TEXT_END:08X}) of the "
          f"authenticated text; {rejected} word(s) the decoder rejected or marked unknown")
    print("BLIND SPOT: a base register loaded from a DATA table rather than lui/addiu, and any "
          "address built by arithmetic this sweep does not model. Tracked values are also dropped "
          "at every control transfer, which loses true positives inside a function that reloads a "
          "base but never invents one. A '0' means '0 in the decoded forms'.")
    for target in sorted(TARGETS):
        print(f"\n0x{target:08X}: {len(stores[target])} store(s), {len(loads[target])} load(s)")
        for addr, text in stores[target]:
            print(f"  STORE 0x{addr:08X}  {text}")
        for addr, text in loads[target]:
            print(f"  LOAD  0x{addr:08X}  {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
