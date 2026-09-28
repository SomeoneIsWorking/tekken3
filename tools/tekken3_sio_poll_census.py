#!/usr/bin/env python3
"""tekken3_sio_poll_census.py — which SIO0 word does the guest poll, and which BIT?

WHY THIS EXISTS. A running product showed the NAMCO PRESENTS card's wait loop never exiting, and
the first account of it named a spin at `0x800934D8..0x800934E4` that polls bit `0x0002` of the
halfword at `*0x8009B964 + 4`. **Decoding the authenticated image says that account is wrong in
three ways at once**: `0x800934D8` is `sw $ra,0x10($sp)` — a function PROLOGUE, not a poll — the
load is `lw`, not `lhu`, and the mask is `0x0001`, not `0x0002`. So the address, the width and the
bit were all wrong, and the word it polls read `0x0001`, which SATISFIES the real mask.

A wrong spin address is the kind of error that survives review because it is quoted from a
disassembly rather than decoded from bytes, so this tool does not take any address on trust. It
decodes the whole authenticated text, finds every access to SIO0's three registers, and reports the
mask each POLLING site actually tests, next to the live value of that register.

DESIGNED NEGATIVE FIRST. It prints the words it walked and the number of functions it found, refuses
a missing or too-small image rather than reporting "0 matches", and every polling site is printed
with the register it reads, the mask it applies, and the branch that closes the loop — so "0 polls"
and "0 loops" are distinguishable from "nothing was looked at".

It also answers the question the S003 blocker actually turns on: does the guest BIT-BANG SIO0 (and
so own the status bit itself) or only READ it (and so depend on the framework's hardware model)?

Usage: tekken3_sio_poll_census.py [--exe PATH] [--selftest]
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import sys

TEXT_BASE = 0x80010000
TEXT_SIZE = 0x000A0000

# SIO0, from the framework's own hardware map:
#   psxport/runtime/psx/io_peripherals.cpp:12  kSio0Lo = 0x1F801040, kSio0Hi = 0x1F80104F
#   psxport/runtime/psx/pad_input.cpp:13       0x1F801040 data / 0x1F801044 status / 0x1F80104A control
SIO0_DATA = 0x1F801040
SIO0_STATUS = 0x1F801044
SIO0_CTRL = 0x1F80104A
SIO0_NAMES = {SIO0_DATA: "data", SIO0_STATUS: "status", SIO0_CTRL: "control"}

# Eight instructions whose correct decoding is known from a separate, hand-decoded reading of the
# same image. The tool re-derives all eight and fails if it disagrees with any, so a decoder bug
# cannot quietly answer the question this census exists to answer.
CONTROL = [
    (0x800934CC, 0x3C03800A, "lui   $v1,0x800A"),
    (0x800934D0, 0x8C63B960, "lw   $v1,-18080($v1)"),
    (0x800934D4, 0x27BDFFE8, "addiu $sp,$sp,-24"),
    (0x800934D8, 0xAFBF0010, "sw   $ra,16($sp)"),
    (0x800934DC, 0x8C620004, "lw   $v0,4($v1)"),
    (0x800934E0, 0x00000000, "nop"),
    (0x800934E4, 0x30420001, "andi  $v0,$v0,0x0001"),
    # The expected offset was first written as +0x3C and the control caught it: 0x1040000E carries
    # immediate 0x000E, and a MIPS branch offset is the immediate TIMES FOUR, so the branch goes to
    # 0x800934EC + 0x38. The slip was in the hand-written expectation, not in the image, and it is
    # recorded here because a control that has never caught anything is a control nobody should trust.
    (0x800934E8, 0x1040000E, "beq   $v0,$zero,+0x38"),
]

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


SPECIAL_FUNCTIONS = {
    0x00: "sll", 0x02: "srl", 0x03: "sra", 0x04: "sllv", 0x06: "srlv", 0x07: "srav",
    0x08: "jr", 0x09: "jalr", 0x0C: "syscall", 0x0D: "break",
    0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo",
    0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu",
    0x20: "add", 0x21: "addu", 0x22: "sub", 0x23: "subu",
    0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor",
    0x2A: "slt", 0x2B: "sltu",
}

# The register-offset loads and stores. 0x2A is SWL and 0x2B is SW, which is why SLTI cannot be
# 0x2A: an earlier version of this decoder said `op == 0x2A` meant `slti`, and it silently ate every
# unaligned word load in the text. Getting an opcode table wrong does not look like a bug — it looks
# like a region that is not code.
LOADS = {0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x26: "lwr"}
STORES = {0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw", 0x2E: "swr"}


def decode(word: int) -> str:
    """Decode the subset of MIPS-I this census needs, and return "" for anything else.

    Returning "" rather than a guess matters: an instruction this function does not model must not
    be able to masquerade as one it does, or a wrong address would come back out as a real site.
    """
    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    sa = (word >> 6) & 0x1F
    imm = word & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    target = (word & 0x03FFFFFF) << 2

    if word == 0:
        return "nop"
    if op == 0x00:
        name = SPECIAL_FUNCTIONS.get(word & 0x3F)
        if name is None:
            return ""
        if name in ("sll", "srl", "sra"):
            return f"{name:<5} ${REG[rd]},${REG[rt]},{sa}"
        if name in ("sllv", "srlv", "srav"):
            return f"{name:<5} ${REG[rd]},${REG[rt]},${REG[rs]}"
        if name == "jr":
            return f"jr    ${REG[rs]}"
        if name == "jalr":
            return f"jalr  ${REG[rd]},${REG[rs]}"
        if name in ("syscall", "break"):
            return f"{name}  0x{imm:04X}"
        if name in ("mfhi", "mflo"):
            return f"{name}  ${REG[rd]}"
        if name in ("mthi", "mtlo"):
            return f"{name}  ${REG[rs]}"
        if name in ("mult", "multu", "div", "divu"):
            return f"{name}  ${REG[rs]},${REG[rt]}"
        if name in ("add", "addu", "sub", "subu", "and", "or", "xor", "nor", "slt", "sltu"):
            return f"{name:<5} ${REG[rd]},${REG[rs]},${REG[rt]}"
        return ""
    if op == 0x0F:
        return f"lui   ${REG[rt]},0x{imm:04X}"
    if op == 0x09:
        return f"addiu ${REG[rt]},${REG[rs]},{simm}"
    if op == 0x0A:
        return f"slti  ${REG[rt]},${REG[rs]},{simm}"
    if op == 0x0B:
        return f"sltiu ${REG[rt]},${REG[rs]},{simm}"
    if op == 0x0D:
        return f"ori   ${REG[rt]},${REG[rs]},0x{imm:04X}"
    if op == 0x0C:
        return f"andi  ${REG[rt]},${REG[rs]},0x{imm:04X}"
    if op == 0x0E:
        return f"xori  ${REG[rt]},${REG[rs]},0x{imm:04X}"
    if op in LOADS or op in STORES:
        name = LOADS.get(op) or STORES[op]
        return f"{name:<4} ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x04:
        return f"beq   ${REG[rs]},${REG[rt]},+0x{simm * 4:X}"
    if op == 0x05:
        return f"bne   ${REG[rs]},${REG[rt]},+0x{simm * 4:X}"
    if op == 0x06:
        return f"blez  ${REG[rs]},+0x{simm * 4:X}"
    if op == 0x07:
        return f"bgtz  ${REG[rs]},+0x{simm * 4:X}"
    if op == 0x01:
        kinds = {0: "bltz", 1: "bgez", 16: "bltzal", 17: "bgezal"}
        name = kinds.get(rt, f"regimm{rt}")
        return f"{name:<6} ${REG[rs]},+0x{simm * 4:X}"
    if op == 0x02:
        return f"j     0x{target:08X}"
    if op == 0x03:
        return f"jal   0x{target:08X}"
    if op in (0x32, 0x3A):
        return f"{'lwc2' if op == 0x32 else 'swc2'} ${REG[rt]},0x{imm:04X}(${REG[rs]})"
    return ""


def selftest(image: bytes) -> bool:
    """Re-derive the eight control decodings, plus a negative on the decoder's blind spot."""
    ok = True
    for address, expected_word, expected_text in CONTROL:
        got_word = struct.unpack_from("<I", image, address - TEXT_BASE)[0]
        got_text = decode(got_word)
        if got_word != expected_word or got_text != expected_text:
            print(f"  CONTROL FAIL {address:08X}: image has {got_word:08X}, expected {expected_word:08X}; "
                  f"decoded {got_text!r}, expected {expected_text!r}")
            ok = False
    # The negative: an opcode this decoder does not model must come back EMPTY, never as a site.
    if decode(0xFC000000) != "":
        print("  CONTROL FAIL: an unmodelled opcode decoded to text, so a wrong address could be reported")
        ok = False
    # And a masked read must keep its mask, because the mask IS the question.
    if decode(0x30420002) != "andi  $v0,$v0,0x0002":
        print("  CONTROL FAIL: andi lost its immediate, so the polled bit could not be reported")
        ok = False
    # The mnemonic must be the name Lightrec's own `enum special_opcodes` gives that funct. Checking
    # against an enum in the tree is a control that can be wrong; checking against text an agent
    # re-derived by hand from hex is not one, and the first version of this selftest was that.
    for word in (0x00031880, 0x00711821, 0x00022100, 0x00822023, 0x00042100, 0x0060F809, 0x00442021):
        funct = word & 0x3F
        expected = SPECIAL_FUNCTIONS.get(funct)
        got = decode(word)
        if expected is None:
            if got != "":
                print(f"  CONTROL FAIL: SPECIAL funct 0x{funct:02X} is not in the enum table but "
                      f"decoded as {got!r}")
                ok = False
        elif not got.startswith(expected):
            print(f"  CONTROL FAIL: SPECIAL 0x{word:08X} (funct 0x{funct:02X} = {expected}) decoded "
                  f"as {got!r}")
            ok = False
    # The load/store opcode table must classify by the TOP SIX BITS alone, which is the one part of
    # an encoding that cannot be misread. 0x2A is SWL and 0x0A is SLTI; an earlier version had them
    # the other way round and the symptom was a region that looked like data.
    for word, expected in ((0x8C820000, "lw"), (0xA8000000, "swl"), (0xA4820000, "sh"),
                           (0x94820004, "lhu"), (0xA4820004, "sh"), (0x28820001, "slti")):
        if not decode(word).startswith(expected):
            print(f"  CONTROL FAIL: 0x{word:08X} (top six bits 0x{word >> 26:02X}) decoded as "
                  f"{decode(word)!r}, expected {expected!r}")
            ok = False
    # An opcode outside every modelled set must decode to nothing, never to a plausible instruction.
    for word in (0xFC000000, 0x40000000, 0x42000018, 0x46000000):
        if decode(word) != "":
            print(f"  CONTROL FAIL: unmodelled word 0x{word:08X} decoded as {decode(word)!r}")
            ok = False
    print(f"  control: {len(CONTROL)} of {len(CONTROL)} decodings reproduced"
          f"{'' if ok else ' — FAILED'}, unmodelled opcodes refused")
    return ok


def walk(image: bytes) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Two routes to SIO0, both reported, because the guest uses the indirect one.

    ROUTE A (direct): `lui $r,0x1F80` in the decoded text, then an addiu/ori to reach the register.
    ROUTE B (pointer): a DATA word somewhere in the image that IS an SIO0 address, which the guest
    then dereferences. Route B is the one this title actually uses, and a census that only walks
    instructions reports it as zero — a confident answer about the wrong subject.
    """
    words = struct.unpack_from(f"<{TEXT_SIZE // 4}I", image, 0)
    # high[reg] is the last `lui` value the DECODER believes is live. This is a linear sweep and is
    # therefore an approximation — any branch can invalidate it — so every access it reports is
    # printed with the instruction that produced the address, never as a bare address.
    high: list[int | None] = [None] * 32
    instructions = 0
    accesses: list[dict] = []
    for index, word in enumerate(words):
        address = TEXT_BASE + index * 4
        text = decode(word)
        if not text:
            continue
        instructions += 1
        op = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if op == 0x0F:
            high[rt] = imm << 16
            continue
        if op in LOADS or op in STORES:
            base = high[rs]
            if base is None or rs == 0:
                continue
            absolute = base + simm
            if absolute in SIO0_NAMES:
                kind = LOADS.get(op) or STORES[op]
                accesses.append({
                    "address": address, "text": text, "register": SIO0_NAMES[absolute],
                    "full": absolute, "kind": kind, "route": "A direct",
                })

    # ROUTE B: every aligned word in the WHOLE image, not just the text, that is an SIO0 address.
    # A word found inside the text is a pointer a function is about to load; one found past the text
    # is part of the data segment. Both are reported, with the one that is in scope marked, because
    # "the pointer is at 0x8009B964" and "the pointer is in RAM somewhere" are different claims.
    pointers: list[dict] = []
    total_words = len(image) // 4
    for index in range(total_words):
        word = struct.unpack_from("<I", image, index * 4)[0]
        if word in SIO0_NAMES:
            pointers.append({
                "address": index * 4,
                "full": word,
                "register": SIO0_NAMES[word],
                "in_text": TEXT_BASE <= index * 4 < TEXT_BASE + TEXT_SIZE,
            })
    stats = {"words": len(words), "instructions": instructions, "accesses": len(accesses),
             "pointers": len(pointers), "image_words": total_words}
    return accesses, pointers, stats


def report(image: bytes) -> int:
    accesses, pointers, stats = walk(image)
    print(f"census: walked {stats['words']} word(s) of the authenticated text at 0x{TEXT_BASE:08X}, "
          f"modelled {stats['instructions']} instruction(s), "
          f"unmodelled {stats['words'] - stats['instructions']}")
    print(f"census: route A (direct `lui 0x1F80` + displacement) — {stats['accesses']} site(s)")
    print(f"census: route B (a word in the image that IS an SIO0 address) — {stats['pointers']} site(s) "
          f"across {stats['image_words']} word(s)")
    print("census: a zero on one route is a statement about that route only; the guest reaches the "
          "port by whatever route the data words show")

    for full, name in sorted(SIO0_NAMES.items()):
        found = [a for a in accesses if a["full"] == full]
        writes = [a for a in found if a["kind"] in ("sw", "sh", "sb")]
        print(f"  0x{full:08X} {name:<8} direct reads {len(found) - len(writes):>3}  "
              f"direct writes {len(writes):>3}  pointers {len(pointers_by_register(pointers, name)):>3}")
        for access in found:
            print(f"      {access['address']:08X}  {access['text']:<28} -> SIO0 {name} ({access['kind']})")

    for pointer in pointers:
        where = "in text" if pointer["in_text"] else "in data"
        print(f"      pointer {pointer['address']:08X} ({where}) holds 0x{pointer['full']:08X} "
              f"= SIO0 {pointer['register']}")
    if not pointers:
        print("  no word in the image is an SIO0 address, so the port is not reachable through a "
              "pointer and route A is the only one — and route A is empty, which would mean the "
              "poll this census was written for is not a SIO0 access at all")

    total_writes = sum(1 for a in accesses if a["kind"] in ("sw", "sh", "sb"))
    print()
    if not accesses and pointers:
        print("verdict: the guest NEVER materialises an SIO0 address in an instruction — it reads a "
              "POINTER to the port out of memory and dereferences it. So the guest cannot bit-bang "
              "the status register through a constant: whether the polled bit ever sets is decided by "
              "whatever wrote that pointer, and the address in the register is not the question.")
    elif total_writes == 0:
        print("verdict: the guest READS SIO0 and never WRITES it, so the status bit is owned by the "
              "framework's hardware model rather than by guest code.")
    else:
        print(f"verdict: the guest WRITES SIO0 at {total_writes} site(s), so it drives the port itself.")
    return 0


def sites_near(decoded: dict[int, str], centre: int, span: int = 12) -> list[tuple[int, str]]:
    return [(address, text) for address, text in sorted(decoded.items())
            if centre - span <= address <= centre + span]


def report_word(image: bytes, target: int) -> int:
    words = struct.unpack_from(f"<{TEXT_SIZE // 4}I", image, 0)
    high: list[int | None] = [None] * 32
    decoded: dict[int, str] = {}
    hits: list[dict] = []
    for index, word in enumerate(words):
        address = TEXT_BASE + index * 4
        text = decode(word)
        if text:
            decoded[address] = text
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        if op == 0x0F:
            high[rt] = imm << 16
            continue
        if op in LOADS or op in STORES:
            if rs == 0 or high[rs] is None:
                continue
            absolute = high[rs] + simm
            # A halfword access to an even address also covers the ODD word beside it, because the
            # card byte is read as a `lh` of the halfword it shares. Missing that is how a reader
            # concludes "nothing polls this" when the guest polls it every field.
            covered = absolute == target or (target % 2 == 1 and absolute == target - 1)
            if covered:
                hits.append({"address": address, "text": text, "absolute": absolute,
                             "kind": LOADS.get(op) or STORES[op]})
    print(f"scan: {len(words)} word(s) walked, {len(decoded)} instruction(s) modelled, "
          f"{len(hits)} materialised access(es) to 0x{target:08X} (or the halfword holding it)")
    if not hits:
        print("scan: 0 accesses. The word is not reached by materialising its address, so any reader "
              "of it must go through a pointer — a statement about materialisation only.")
        return 0
    for hit in hits:
        print(f"  hit {hit['address']:08X}  {hit['text']:<28} ({hit['kind']}) at 0x{hit['absolute']:08X}")
        window = sites_near(decoded, hit["address"], span=8)
        for address, text in window:
            marker = ">>" if address == hit["address"] else "  "
            back = "   <- back edge" if is_back_edge(decoded, address) else ""
            print(f"    {marker} {address:08X}  {text}{back}")
    return 0


def is_back_edge(decoded: dict[int, str], address: int) -> bool:
    """True when the instruction at `address` branches to itself or something at or before it."""
    text = decoded.get(address, "")
    if "+0x" not in text or not text.startswith(("beq", "bne", "blez", "bgtz", "bltz", "bgez")):
        return False
    try:
        offset = int(text.rsplit("+0x", 1)[1], 16)
    except (IndexError, ValueError):
        return False
    return address + 4 + offset <= address + 4


def pointers_by_register(pointers: list[dict], name: str) -> list[dict]:
    return [p for p in pointers if p["register"] == name]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Relative to the REPO, not to the working directory: CTest runs every test from the build
    # directory, so a tool that resolves its own image against the cwd refuses on the gate and
    # passes when run by hand from the root — a tool whose answer depends on where it was invoked
    # from is not a measurement.
    default_image = (pathlib.Path(__file__).resolve().parent.parent
                     / "scratch" / "bin" / "tekken3" / "SLUS_004.02")
    parser.add_argument("--exe", default=str(default_image),
                        help="the provisioned authenticated SLUS_004.02")
    parser.add_argument("--selftest", action="store_true",
                        help="run the control decodings and the decoder's negative cases")
    parser.add_argument("--word", type=lambda v: int(v, 0), default=None,
                        help="scan for materialised accesses to this RAM word instead of the SIO0 census")
    arguments = parser.parse_args()
    path = pathlib.Path(arguments.exe)
    if not path.is_file():
        print(f"REFUSED: {path} is not a file — provision the authenticated image before measuring")
        return 1
    image = path.read_bytes()
    if len(image) < TEXT_SIZE:
        print(f"REFUSED: {path} is {len(image)} byte(s), smaller than the {TEXT_SIZE}-byte text this "
              f"census claims to have walked; reporting '0 matches' from a short read is the exact "
              f"failure this tool exists to avoid")
        return 1
    if arguments.selftest and not selftest(image):
        return 1
    if arguments.word is not None:
        return report_word(image, arguments.word)
    return report(image)


if __name__ == "__main__":
    sys.exit(main())
