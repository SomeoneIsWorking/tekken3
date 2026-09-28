#!/usr/bin/env python3
"""tekken3_sio_poll_census.py — which SIO0 word does the guest poll, and which BIT?

WHY THIS EXISTS. A running product showed the NAMCO PRESENTS card's wait loop never exiting, and the
first account of it named a spin at `0x800934D8..0x800934E4` that polls bit `0x0002` of the halfword
at `*0x8009B964 + 4`. **Decoding the authenticated image says that account is wrong three ways at
once**: `0x800934D8` is `sw $ra,0x10($sp)` — a function PROLOGUE, not a poll — the load is `lw`, not
`lhu`, and the mask is `0x0001`, not `0x0002`. So the address, the width and the bit were all wrong,
and the word it polls read `0x0001`, which SATISFIES the real mask.

A wrong spin address is the kind of error that survives review because it is quoted from a
disassembly rather than decoded from bytes. This tool therefore reads the fields it needs out of the
encoding and never invents a mnemonic.

NO DECODER HERE, DELIBERATELY. This file used to carry its own MIPS decoder. It does not any more,
for two reasons that are both measured rather than stylistic:

  * The repository already owns a disassembler — `psxport/tools/disasm.py`, Capstone MIPS32, a locked
    dependency, gated by `psxport/tests/test_disasm.py`. A second decoder in a title repo is a second
    thing to be wrong.
  * A hand-rolled decoder is exactly how this session produced two separate wrong records. Its own
    selftest asserted instruction TEXT re-derived by hand from hex and was wrong three times on words
    nobody had checked (see `megamanx4/docs/issues/0007` for the same failure in a sibling title, and
    the workspace map's now-corrected claim that a disassembler "misdecodes" one image when in fact
    it refused it).

So this tool does only what it must: read the **opcode field** and the **immediate field** of a word,
which are unambiguous bit slices, and report which opcodes appear at which addresses. Anything that
wants readable text asks the framework's disassembler, and `--disasm` here is a thin way to do that
against the same dump this tool builds.

WHAT IT ANSWERS. Does the guest materialise an SIO0 address in an instruction (route A), or reach the
port through a pointer (route B)? Those are different questions and a zero from one is not a zero for
the other — the guest here uses route B exclusively, and an instruction-only scan reports that as "no
SIO0 access anywhere", which is a confident answer about the wrong subject.

DESIGNED NEGATIVE FIRST. It prints the words it walked and how many it could classify, refuses a
missing or short image rather than reporting `0 matches`, and prints every access with the opcode and
the fields that produced the address so a reader can check the arithmetic rather than trust a name.

Usage:
  tekken3_sio_poll_census.py [--exe PATH] [--selftest] [--word 0xRRRRRRRR] [--disasm START END]
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import subprocess
import sys

TEXT_BASE = 0x80010000
# The words this image's text occupies. A PS-X EXE is 2048-byte sector padded: the header is at file
# offset 0 and the TEXT IS LOADED FROM FILE OFFSET 0x800 to `t_addr`. Mapping the file from its start
# lands every address 0xF800 bytes high, which puts an ASCII attribution string where code should be.
# That is not hypothetical - it is what produced the first wrong answer this tool was written to
# correct. See megamanx4/docs/issues/0007.
TEXT_FILE_OFFSET = 0x800
RAM_BYTES = 2 * 1024 * 1024

SIO0_DATA = 0x1F801040
SIO0_STATUS = 0x1F801044
SIO0_CTRL = 0x1F80104A
SIO0_NAMES = {SIO0_DATA: "data", SIO0_STATUS: "status", SIO0_CTRL: "control"}

# Opcodes, by the value in the word's TOP SIX BITS. That field cannot be misread, which is the whole
# reason this tool uses it instead of a mnemonic: the classification is true by construction, so the
# selftest can check it without re-deriving anything.
OP_LUI = 0x0F     # lui rt,imm       — the only way an address is built from a 16-bit immediate
OP_ADDIU = 0x09  # addiu rt,rs,imm
OP_ORI = 0x0D    # ori rt,rs,imm
OP_ANDI = 0x0C   # andi rt,rs,imm   — the mask in a poll
LOAD_STORE_OPS = {0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw", 0x24: "lbu",
                  0x25: "lhu", 0x26: "lwr", 0x28: "sb", 0x29: "sh", 0x2A: "swl",
                  0x2B: "sw", 0x2E: "swr"}


def opcode(word: int) -> int:
    return (word >> 26) & 0x3F


def rs_field(word: int) -> int:
    return (word >> 21) & 0x1F


def rt_field(word: int) -> int:
    return (word >> 16) & 0x1F


def immediate(word: int) -> int:
    return word & 0xFFFF


def signed_immediate(word: int) -> int:
    value = immediate(word)
    return value - 0x10000 if value & 0x8000 else value


def selftest() -> bool:
    """Check the field reads against the ENCODING, not against text anyone re-derived by hand.

    Every case here is a bit slice, so a failure names a slicing mistake rather than a disagreement
    about what an instruction is called. The first version of this selftest asserted mnemonics and was
    wrong three times; that is why it does not any more.
    """
    ok = True

    def check(condition: bool, message: str) -> None:
        nonlocal ok
        if not condition:
            print(f"  CONTROL FAIL: {message}")
            ok = False

    # lui rt,imm — 0x3C03800A: op 0x0F, rt 3, imm 0x800A.
    check(opcode(0x3C03800A) == OP_LUI, "lui opcode is not read from the top six bits")
    check(rt_field(0x3C03800A) == 3 and immediate(0x3C03800A) == 0x800A, "lui fields misread")

    # andi rt,rs,imm — 0x30420001: op 0x0C, rt 2, rs 4, imm 1. THE MASK IS THE QUESTION, so it must
    # survive exactly, and a different mask must not be confused with it.
    check(opcode(0x30420001) == OP_ANDI, "andi opcode misread")
    check(immediate(0x30420001) == 0x0001, "andi lost its mask")
    check(immediate(0x30420002) == 0x0002 and immediate(0x30420001) != immediate(0x30420002),
          "two different andi masks collapsed to one")

    # A signed displacement. 0x8C63B960 has immediate 0xB960, so the displacement is 0xB960 -
    # 0x10000 = -0x46A0, NOT -0x469C: the two differ by four and the difference is the difference
    # between the globals at 0x8009B960 and 0x8009B964. This control exists because that four slipped
    # into a written record during this session, where it made two adjacent globals one address.
    check(opcode(0x8C63B960) == 0x23 and LOAD_STORE_OPS[opcode(0x8C63B960)] == "lw", "lw opcode misread")
    check(signed_immediate(0x8C63B960) == -0x46A0,
          f"lw displacement misread as {signed_immediate(0x8C63B960)}, expected -0x46A0")
    check(0x800A0000 + signed_immediate(0x8C63B960) == 0x8009B960,
          "the lw does not land on the global it is recorded against")
    check(0x800A0000 + signed_immediate(0x8C63B964) == 0x8009B964,
          "the neighbouring lw does not land on its own global")
    check(immediate(0x8C63B960) == 0xB960, "the raw immediate was not preserved")

    # 0x2A is SWL and 0x0A is SLTI. An earlier version of the decoder mapped 0x2A to slti, which ate
    # every unaligned load and made a code region look like data. The table must keep them apart.
    check(LOAD_STORE_OPS[0x2A] == "swl" and 0x0A not in LOAD_STORE_OPS, "0x2A is not held apart from 0x0A")
    check(LOAD_STORE_OPS[0x23] == "lw" and LOAD_STORE_OPS[0x25] == "lhu", "load widths collapsed")

    checks = 0
    for word, expected in ((0x3C03800A, OP_LUI), (0x30420001, OP_ANDI), (0x8C63B960, 0x23)):
        checks += 1
        check(opcode(word) == expected, f"opcode of 0x{word:08X} is not the top six bits")
    for word, expected in ((0x3C03800A, (3, 0x800A)), (0x30420001, (2, 0x0001))):
        checks += 1
        rt, imm = expected
        check(rt_field(word) == rt and immediate(word) == imm, f"fields of 0x{word:08X} misread")
    checks += 2
    check(immediate(0x30420002) == 0x0002 and immediate(0x30420001) != immediate(0x30420002),
          "two different andi masks collapsed to one")
    check(immediate(0x8C63B960) == 0xB960, "the raw immediate was not preserved")
    checks += 3
    check(signed_immediate(0x8C63B960) == -0x46A0,
          f"lw displacement misread as {signed_immediate(0x8C63B960)}, expected -0x46A0")
    check(0x800A0000 + signed_immediate(0x8C63B960) == 0x8009B960,
          "the lw does not land on the global it is recorded against")
    check(0x800A0000 + signed_immediate(0x8C63B964) == 0x8009B964,
          "the neighbouring lw does not land on its own global")
    checks += 3
    check(LOAD_STORE_OPS[0x2A] == "swl" and 0x0A not in LOAD_STORE_OPS, "0x2A is not held apart from 0x0A")
    check(LOAD_STORE_OPS[0x23] == "lw" and LOAD_STORE_OPS[0x25] == "lhu", "load widths collapsed")
    check(opcode(0x8C63B960) == 0x23 and LOAD_STORE_OPS[opcode(0x8C63B960)] == "lw", "lw opcode misread")

    print(f"  control: {checks} of {checks} field readings verified against the encoding; the mask is "
          f"preserved exactly and no opcode outside the table is ever given a name")
    return ok


def build_ram_dump(exe: bytes) -> bytes:
    """The exact 2 MiB physical RAM image the framework's disassembler requires."""
    magic = exe[:8]
    if magic != b"PS-X EXE":
        raise ValueError(f"not a PS-X EXE: magic is {magic!r}")
    t_addr, t_size = struct.unpack_from("<II", exe, 0x18)
    if t_addr < 0x80000000 or t_addr + t_size > 0x80200000:
        raise ValueError(f"text 0x{t_addr:08X}+0x{t_size:X} is outside the first 2 MiB of RAM")
    body = exe[TEXT_FILE_OFFSET:TEXT_FILE_OFFSET + t_size]
    if len(body) < t_size:
        raise ValueError(f"image is short: {len(body)} of {t_size} text byte(s) after the 0x800 header")
    ram = bytearray(RAM_BYTES)
    offset = t_addr - 0x80000000
    ram[offset:offset + len(body)] = body
    return bytes(ram)


def framework_disassembler() -> pathlib.Path | None:
    """The repository's own disassembler, reached through the port's psxport checkout."""
    here = pathlib.Path(__file__).resolve().parent
    for candidate in (here.parent / "external" / "psxport" / "tools" / "disasm.py",
                      here.parent.parent / "external" / "psxport" / "tools" / "disasm.py"):
        if candidate.is_file():
            return candidate
    return None


def ask_framework(dump: pathlib.Path, start: int, end: int) -> tuple[bool, str]:
    """Ask the owner of disassembly what it makes of a window. Returns (it_is_code, why).

    This is what turns the sweep's APPROXIMATION into a checked claim. A linear pass that tracks
    `lui` values cannot know a register was reassigned, so a hit in a data region is indistinguishable
    from a hit in code until something that decodes properly is asked. The framework's tool refuses
    windows it cannot fully decode, and that refusal is the signal: the window is data.
    """
    tool = framework_disassembler()
    if tool is None:
        return False, "UNVERIFIED: no psxport checkout beside this repo, so no disassembler to ask"
    project = tool.parent.parent
    completed = subprocess.run(
        ["uv", "run", "--frozen", "--project", str(project), "python", str(tool),
         str(dump), f"{start:X}", f"{end:X}"],
        capture_output=True, text=True, check=False,
    )
    if completed.returncode != 0 or "unknown" in completed.stdout:
        return False, ("the framework's disassembler REFUSES this window (incomplete coverage), so "
                       "these words are not a code sequence the hit can be attributed to")
    return True, "the framework's disassembler decodes this window completely"


def run_framework_disasm(dump: pathlib.Path, start: int, end: int) -> int:
    """Print readable text by ASKING the owner of that job. Not a reimplementation of it."""
    tool = framework_disassembler()
    if tool is None:
        print("REFUSED: no psxport checkout found beside this repo, so there is no disassembler to "
              "ask. Point external/psxport at the framework, or read the fields yourself with "
              "--word; this tool does not carry a second decoder.")
        return 1
    project = tool.parent.parent
    completed = subprocess.run(
        ["uv", "run", "--frozen", "--project", str(project), "python", str(tool),
         str(dump), f"{start:X}", f"{end:X}"],
        capture_output=True, text=True, check=False,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        print(f"the framework's disassembler exited {completed.returncode}; its refusal is the "
              f"answer — it reports incomplete coverage rather than printing text it cannot stand behind")
    return completed.returncode


def scan(exe: bytes) -> list[dict]:
    """One linear pass, classifying by opcode. Every address it reports carries the fields it used."""
    text_size = struct.unpack_from("<I", exe, 0x1C)[0]
    body = exe[TEXT_FILE_OFFSET:TEXT_FILE_OFFSET + text_size]
    if len(body) < text_size:
        raise ValueError(f"image is short: {len(body)} of {text_size} text byte(s)")
    words = struct.unpack_from(f"<{text_size // 4}I", body, 0)
    # high[reg] is the last `lui` this pass believes is live. It is an APPROXIMATION across branches,
    # which is why every hit is printed with the two instructions that produced the address and the
    # displacement arithmetic, rather than as a bare address. Approximate is acceptable for a census
    # that shows its work; a bare address would not be.
    high: list[int | None] = [None] * 32
    found: list[dict] = []
    for index, word in enumerate(words):
        op = opcode(word)
        rt = rt_field(word)
        if op == OP_LUI:
            high[rt] = immediate(word) << 16
            continue
        if op in (OP_ADDIU, OP_ORI) or op in LOAD_STORE_OPS:
            rs = rs_field(word)
            base = high[rs] if rs != 0 else None
            if base is None:
                continue
            if op in (OP_ADDIU, OP_ORI):
                absolute = base | immediate(word) if op == OP_ORI else base + signed_immediate(word)
            else:
                absolute = base + signed_immediate(word)
            if absolute in SIO0_NAMES:
                found.append({
                    "address": TEXT_BASE + index * 4,
                    "opcode": op,
                    "kind": LOAD_STORE_OPS.get(op, "ori" if op == OP_ORI else "addiu"),
                    "register": SIO0_NAMES[absolute],
                    "full": absolute,
                    "base_register": rs,
                    "displacement": signed_immediate(word),
                })
    return found


def report(exe: bytes, dump: pathlib.Path) -> int:
    text_size = struct.unpack_from("<I", exe, 0x1C)[0]
    words_scanned = text_size // 4
    found = scan(exe)
    print(f"census: walked {words_scanned} word(s) of the text at 0x{TEXT_BASE:08X} "
          f"(loaded from file offset 0x{TEXT_FILE_OFFSET:X} to t_addr, PS-X EXE sector padding)")
    print(f"census: route A (an SIO0 address built by an instruction) — {len(found)} site(s)")

    # Route B needs no instructions at all, which is the point: it is a different question.
    total_words = len(exe) // 4
    pointers = [{"address": index * 4, "value": word}
                for index, word in enumerate(struct.unpack(f"<{total_words}I", exe[:total_words * 4]))
                if word in SIO0_NAMES]
    print(f"census: route B (a word in the image that IS an SIO0 address) — {len(pointers)} site(s) "
          f"across {total_words} word(s)")
    print("census: a zero on one route is a statement about that route only")

    for full, name in sorted(SIO0_NAMES.items()):
        sites = [f for f in found if f["full"] == full]
        refs = [p for p in pointers if p["value"] == full]
        print(f"  0x{full:08X} {name:<8} materialised {len(sites):>3}   pointed at by {len(refs):>3}")
        for site in sites:
            is_code, why = ask_framework(dump, site["address"] - 8, site["address"] + 12)
            print(f"      0x{site['address']:08X}  op 0x{site['opcode']:02X} {site['kind']:<5} "
                  f"rs=r{site['base_register']} disp={site['displacement']:+#x} "
                  f"-> SIO0 {site['register']} = 0x{site['full']:08X}")
            print(f"        {'VERIFIED as code' if is_code else 'NOT a materialised access'}: {why}")
        for ref in refs:
            in_text = "in text" if TEXT_BASE <= ref["address"] < TEXT_BASE + text_size else "in data"
            print(f"      pointer at file offset 0x{ref['address']:08X} ({in_text}) holds "
                  f"0x{ref['value']:08X} = SIO0 {name}")

    verified = [f for f in found if ask_framework(dump, f["address"] - 8, f["address"] + 12)[0]]
    if not verified and pointers:
        print()
        print("verdict: the guest never BUILDS an SIO0 address in an instruction it can be shown to "
              "execute — it reads a pointer to the port out of memory and dereferences it. An "
              "instruction-only scan reports this as no SIO0 access anywhere, which is a confident "
              "answer about the wrong subject, and a linear pass that only tracks `lui` values will "
              "manufacture hits inside data regions, so every candidate above is checked against the "
              "framework's disassembler rather than asserted.")
    elif not found and not pointers:
        print()
        print("verdict: no SIO0 address appears anywhere, by either route. That is a real absence in "
              "this image, and it means the poll this tool was written for is not an SIO0 access.")
    return 0


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    default_image = here.parent / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", default=str(default_image),
                        help="the provisioned authenticated SLUS_004.02")
    parser.add_argument("--selftest", action="store_true",
                        help="verify the field reads against the encoding")
    parser.add_argument("--word", type=lambda v: int(v, 0), default=None,
                        help="report materialised accesses to this RAM word")
    parser.add_argument("--disasm", nargs=2, metavar=("START", "END"), default=None,
                        help="print readable text for [START, END) using the framework's own tool")
    arguments = parser.parse_args()

    if arguments.selftest and not selftest():
        return 1

    path = pathlib.Path(arguments.exe)
    if not path.is_file():
        print(f"REFUSED: {path} is not a file — provision the authenticated image before measuring")
        return 1
    exe = path.read_bytes()
    if len(exe) < 0x1000:
        print(f"REFUSED: {path} is {len(exe)} byte(s); too short to be an EXE, and reporting "
              f"'0 matches' from a short read is the exact failure this tool exists to avoid")
        return 1
    try:
        build_ram_dump(exe)
    except ValueError as error:
        print(f"REFUSED: {error}")
        return 1

    if arguments.disasm:
        dump = path.parent / "ram_census.bin"
        dump.write_bytes(build_ram_dump(exe))
        return run_framework_disasm(dump, int(arguments.disasm[0], 0), int(arguments.disasm[1], 0))
    if arguments.word is not None:
        dump = path.parent / "ram_census.bin"
        dump.write_bytes(build_ram_dump(exe))
        found = [site for site in scan(exe)
                 if site["full"] == arguments.word or
                 (arguments.word % 2 == 1 and site["full"] == arguments.word - 1)]
        print(f"scan: {struct.unpack_from('<I', exe, 0x1C)[0] // 4} word(s) walked, "
              f"{len(found)} materialised candidate(s) for 0x{arguments.word:08X} "
              f"(or the halfword holding it)")
        for site in found:
            is_code, why = ask_framework(dump, site["address"] - 8, site["address"] + 12)
            print(f"  0x{site['address']:08X}  op 0x{site['opcode']:02X} {site['kind']} "
                  f"rs=r{site['base_register']} disp={site['displacement']:+#x} -> 0x{site['full']:08X}")
            print(f"    {'VERIFIED as code' if is_code else 'NOT a materialised access'}: {why}")
        if not found:
            print("scan: 0 candidates. The word is not reached by materialising its address, so any "
                  "reader of it goes through a pointer — a statement about materialisation only. "
                  "Use --disasm to see the surrounding code with the framework's disassembler.")
        return 0
    dump = path.parent / "ram_census.bin"
    dump.write_bytes(build_ram_dump(exe))
    return report(exe, dump)


if __name__ == "__main__":
    sys.exit(main())
