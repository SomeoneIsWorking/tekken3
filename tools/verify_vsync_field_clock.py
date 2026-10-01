#!/usr/bin/env python3
"""verify_vsync_field_clock.py — does the SHIPPING constant match what the image says it is?

WHY THIS EXISTS. `game/core/vsync_field_clock.h` is a measured fact: 0x8009AC68 is the word Tekken's
linked libetc VSync returns for a negative mode, and the whole title's timeout machinery is timed
against it. A measured constant that ships in code and is never compared against its measurement is
the workspace's most-repeated defect — the tool verifies itself, a static_assert verifies internal
consistency, both gates pass, and the shipping value can be anything. So this tool PARSES the
shipping header and diffs it against what it measures out of the authenticated executable.

It also censuses the VSync call sites, because the declaration is only safe for the modes it was
measured on: 21 of Tekken's 22 VSync calls are negative QUERIES and exactly one waits. If that ratio
changed, "declare the query counter" would no longer be the whole answer, and the tool says so
rather than letting the declaration look unconditional.

The address arithmetic is done from the instruction words, never transcribed. A previous hand
subtraction in this investigation produced 0x800AC68 for `lui 0x800A` + `lw -0x5398`, which is wrong
by 0x1000; Ghidra's own `DAT_8009ac68` was right. Decoding the bytes is the only spelling that
cannot repeat that.

Usage:
    tools/verify_vsync_field_clock.py [--exe PATH] [--header PATH]
    tools/verify_vsync_field_clock.py --selftest [--exe PATH]

The selftest exercises the SHIPPING comparison path, not a helper beside it: it runs the same
check() the normal invocation runs, against a header whose field-counter constant has been perturbed
in a temporary copy, and requires that the tool REJECTS it. It also requires that a byte-perturbed
image is refused by identity. Nothing is edited in the live tree.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/psxport"))

from tools.mips.decode import decode

EXE_DEFAULT = ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
HEADER_DEFAULT = ROOT / "game" / "core" / "vsync_field_clock.h"
MANIFEST = ROOT / "titles" / "tekken3" / "executable.json"

LOAD = 0x80010000
# The PS-X EXE carries a 0x800-byte header in front of the text. Omitting it shifts EVERY decoded
# address while the census still returns confident non-zero counts, so two known instructions are
# reproduced before anything is reported.
HEADER = 0x800
TEXT_SIZE = 0x121000
TEXT_END = LOAD + TEXT_SIZE

# Three instructions copied out of the Ghidra disassembly, not out of this file's own reasoning, and
# deliberately three rather than one: they use two different base registers and three different rt
# fields, so an address-derivation mistake would have to be made identically three times to slip past
# all of them. All three decode to 0x8009AC68, from three unrelated instruction pairs.
GROUND_TRUTH = {
    0x80085A0C: 0x8C42AC68,  # lw v0, -0x5398(v0)  -- the negative-mode field read
    0x8008637C: 0xAC20AC68,  # sw zero, -0x5398(at) -- the library init zeroes the field word
    0x800863DC: 0xAC22AC68,  # sw v0, -0x5398(at)  -- the vblank callback increments it
}

# The measured anchor. Every address below is DERIVED from these instruction addresses by decoding;
# the numbers are cross-checks, not inputs.
VSYNC_NEGATIVE_BRANCH = 0x80085A00  # bgez a0, <the waiting modes>
VSYNC_BRANCH_DELAY = (
    0x80085A04  # andi s1, v0, 0xFFFF -- the waiting modes' return value
)
VSYNC_FIELD_LOAD = 0x80085A0C  # lw v0, disp(v0)     -- the negative-mode field read
VSYNC_FIELD_LOAD_DELAY = 0x80085A10  # j <epilogue>  -- the negative arm returns v0
VSYNC_BODY_END = 0x80085B20  # next function start
VSYNC_INIT_FIELD_STORE = 0x8008637C  # sw zero, disp(at) -- the init
VSYNC_CALLBACK_FIELD_STORE = 0x800863DC  # the per-vblank callback's increment
CALLBACK_BODY = (0x800863B0, 0x8008641C)

# The census this tool exists to keep honest. The tool resolves a site's mode from the call's own
# delay slot or a straight-line backward walk; six sites materialise a0 behind a loop edge, so the
# walk stops and the tool reports them UNRESOLVED rather than guessing. Those six are resolved by
# Ghidra decompilation of their enclosing functions instead: FUN_80083904, FUN_80083B84 and
# FUN_800846D0 each open with `FUN_800859a8(0xffffffff)`, and FUN_800910DC / FUN_80091254 /
# FUN_80091328 pass the same -1.
#
# The gate is the SET, not a count. A new call site that this tool cannot resolve fails, because an
# unexamined site is exactly where a WAIT could hide — and a wait is what "declaring a query counter"
# does not answer.
EXPECTED_TOTAL_SITES = 22
EXPECTED_QUERY_SITES = 21
EXPECTED_WAIT_SITES = 1
# FUN_800B0954's leading VSync(0), inside a function the title already owns natively.
EXPECTED_WAIT_SITE = 0x800B095C
DECOMPILED_RESIDUAL = (
    0x80083938,
    0x80083BB8,
    0x800846F0,
    0x800910F8,
    0x80091288,
    0x8009133C,
)

FIELD_COUNTER_NAME = "kFieldCounter"
ENTRY_NAME = "kEntry"
BODY_END_NAME = "kBodyEnd"


class Refusal(Exception):
    """A refusal is not an empty result; it is reported as one and exits non-zero."""


def load_image(path: pathlib.Path) -> bytes:
    if not path.is_file():
        raise Refusal(
            f"no authenticated executable at {path}. Provision it first; this tool "
            "measures the image and will not answer from a remembered number."
        )
    data = path.read_bytes()
    if len(data) != HEADER + TEXT_SIZE:
        raise Refusal(
            f"{path} is {len(data)} byte(s); the authenticated executable is "
            f"{HEADER + TEXT_SIZE}. NOT MEASURED — this is a refusal, not an empty result."
        )
    return data


def word(data: bytes, addr: int) -> int:
    off = HEADER + addr - LOAD
    if off < 0 or off + 4 > len(data):
        raise Refusal(f"0x{addr:08X} is outside the authenticated text")
    return int.from_bytes(data[off : off + 4], "little")


def decode_at(data: bytes, addr: int):
    return decode(addr, word(data, addr))


def offset_problems(data: bytes) -> list[str]:
    problems = []
    for addr, expected in sorted(GROUND_TRUTH.items()):
        actual = word(data, addr)
        if actual != expected:
            problems.append(
                f"0x{addr:08X}: expected 0x{expected:08X}, read 0x{actual:08X}"
            )
    return problems


def measure_field_counter(data: bytes) -> int:
    """The word a negative VSync mode returns, computed from the instruction that reads it."""
    ins = decode_at(data, VSYNC_FIELD_LOAD)
    if ins.kind != "load" or ins.op != "lw":
        raise Refusal(
            f"0x{VSYNC_FIELD_LOAD:08X} is {ins.kind}/{ins.op}, not the expected lw; the "
            "negative-mode read was not found where the disassembly says it is"
        )
    lui = decode_at(data, VSYNC_FIELD_LOAD - 4)
    if lui.kind != "lui":
        raise Refusal(
            f"0x{VSYNC_FIELD_LOAD - 4:08X} is {lui.kind}, not the expected lui base"
        )
    base = (lui.imm << 16) & 0xFFFFFFFF
    return (base + ins.simm) & 0xFFFFFFFF


def measure_negative_arm_shape(data: bytes) -> list[str]:
    """Prove the field read IS the negative arm's return, not merely some load in the body.

    The claim being made is a five-instruction shape: a signed test on a0 sends every nonnegative
    mode elsewhere, that branch's delay slot is the waiting modes' return value, the field load is
    the fall-through, and the load's own delay slot jumps to the epilogue carrying v0. Checking only
    the lw would leave "VSync(-1) returns this word" resting on an instruction shape nobody verified.
    """
    problems = []
    branch = decode_at(data, VSYNC_NEGATIVE_BRANCH)
    if branch.kind != "branch" or branch.op != "bgez" or branch.rs != 4:
        problems.append(
            f"0x{VSYNC_NEGATIVE_BRANCH:08X} is {branch.kind}/{branch.op} on r{branch.rs}, "
            "not the bgez a0 that separates the waiting modes from the query"
        )
    if branch.kind == "branch" and branch.imm <= 0:
        problems.append(
            f"0x{VSYNC_NEGATIVE_BRANCH:08X} branches backwards (imm={branch.imm}); the "
            "query arm is the fall-through, not a loop"
        )
    delay = decode_at(data, VSYNC_BRANCH_DELAY)
    if delay.kind != "alu_rri" or delay.op != "andi" or delay.imm != 0xFFFF:
        problems.append(
            f"0x{VSYNC_BRANCH_DELAY:08X} is {delay.kind}/{delay.op} imm={delay.imm}, not "
            "the andi 0xFFFF that forms the waiting modes' return value"
        )
    arm_delay = decode_at(data, VSYNC_FIELD_LOAD_DELAY)
    if arm_delay.kind != "jump" or arm_delay.op != "j":
        problems.append(
            f"0x{VSYNC_FIELD_LOAD_DELAY:08X} is {arm_delay.kind}/{arm_delay.op}, not the "
            "unconditional jump to the epilogue that returns the field word"
        )
    return problems


def measure_writers(data: bytes) -> list[tuple[int, int]]:
    """Every lui-base/lw-or-sw pair in the two known writers, decoded to the address it touches."""
    found = []
    for entry in (VSYNC_INIT_FIELD_STORE, VSYNC_CALLBACK_FIELD_STORE):
        store = decode_at(data, entry)
        if store.kind != "store":
            raise Refusal(
                f"0x{entry:08X} is {store.kind}/{store.op}, not the expected store"
            )
        base_ins = decode_at(data, entry - 4)
        if base_ins.kind != "lui":
            raise Refusal(
                f"0x{entry - 4:08X} is {base_ins.kind}, not the lui base for the store"
            )
        found.append((entry, ((base_ins.imm << 16) + store.simm) & 0xFFFFFFFF))
    return found


def literal_mode(ins) -> int | None:
    """The a0 value this instruction materialises, or None if it is not a literal we can name."""
    if ins.kind == "alu_rri" and ins.rs == 0:  # li a0, imm / addiu a0, zero, imm
        return ins.simm
    if ins.kind == "alu_rrr" and ins.rs == 0 and ins.rt == 0:  # addu a0, zero, zero
        return 0
    return None


def writes_a0(ins) -> bool:
    if ins.kind in ("lui", "alu_rri", "load", "gte_move", "gte_load"):
        return ins.rt == 4
    if ins.kind in ("alu_rrr", "shift_i", "shift_v", "muldiv", "gte_op"):
        return 4 in {ins.rd, ins.rt} - {0}
    if ins.kind == "hilo":
        return ins.rd == 4
    return False


def census_vsync_calls(data: bytes, entry: int) -> tuple[list[dict], int]:
    """Every direct jal to the VSync entry, classified by the mode it passes in a0.

    A mode is NAMED only from evidence the tool actually holds: the call's own delay slot, or a
    straight-line walk backwards that meets the a0 write before it meets a control transfer. Crossing
    a branch would mean a different path set the register, so the walk stops there and the site is
    reported UNRESOLVED rather than guessed — six of the twenty-two sites materialise a0 a few
    instructions earlier behind a loop edge, and "I could not read this one" has to read as
    "I could not read this one", not as a zero.
    """
    sites = []
    scanned = 0
    for addr in range(LOAD, TEXT_END, 4):
        raw = word(data, addr)
        scanned += 1
        if (raw >> 26) != 3:  # jal
            continue
        target = ((addr + 4) & 0xF0000000) | ((raw & 0x03FFFFFF) << 2)
        if target != entry:
            continue
        mode = None
        evidence = ""
        delay = decode_at(data, addr + 4)
        mode = literal_mode(delay)
        evidence = f"delay slot {delay.op} r{delay.rs},r{delay.rt},{delay.simm}"
        if mode is None and delay.op not in ("sw", "sh", "sb"):
            mode, evidence = resolve_by_walk(data, addr, 12)
        sites.append({"addr": addr, "mode": mode, "evidence": evidence})
    return sites, scanned


def resolve_by_walk(data: bytes, call: int, limit: int) -> tuple[int | None, str]:
    for back in range(4, 4 * (limit + 1), 4):
        addr = call - back
        try:
            ins = decode_at(data, addr)
        except Refusal:
            return None, f"walked out of the text at 0x{addr:08X}"
        if ins.kind in ("branch", "jump", "jumpr", "syscall", "break_"):
            return None, f"walk stopped at 0x{addr:08X} {ins.kind}/{ins.op}"
        if writes_a0(ins):
            mode = literal_mode(ins)
            if mode is None:
                return (
                    None,
                    f"a0 written non-literally at 0x{addr:08X} {ins.kind}/{ins.op}",
                )
            return mode, f"straight-line {ins.op} at 0x{addr:08X} -> a0={mode}"
    return None, f"no a0 write within {limit} straight-line instruction(s)"


def parse_header(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for name in (ENTRY_NAME, BODY_END_NAME, FIELD_COUNTER_NAME):
        match = re.search(rf"\b{name}\s*=\s*(0x[0-9A-Fa-f]{{8}})u\s*;", text)
        if not match:
            raise Refusal(
                f"the shipping header declares no {name} = 0x........u; nothing was "
                "compared, which is a refusal rather than a pass"
            )
        values[name] = int(match.group(1), 16)
    return values


def check(data: bytes, header_text: str) -> list[str]:
    """THE SHIPPING PATH. Everything this tool asserts goes through here."""
    problems = offset_problems(data)
    if problems:
        # A REFUSAL, not a problem list: nothing below ran, so reporting a diff would be reporting a
        # comparison that never happened. This is the guard that caught a wrong ground-truth constant
        # during development, which is exactly what it is for.
        raise Refusal(
            "the file offset is not pinned, so every address below would be shifted and "
            "wrong: " + "; ".join(problems) + " — NOTHING WAS MEASURED"
        )

    measured_field = measure_field_counter(data)
    writers = measure_writers(data)
    shipping = parse_header(header_text)

    problems = measure_negative_arm_shape(data)
    for entry, touched in writers:
        if touched != measured_field:
            problems.append(
                f"the writer at 0x{entry:08X} touches 0x{touched:08X}, not the measured "
                f"field word 0x{measured_field:08X}"
            )
    sites, scanned = census_vsync_calls(data, shipping[ENTRY_NAME])
    queries = [s for s in sites if s["mode"] is not None and s["mode"] < 0]
    waits = [s for s in sites if s["mode"] is not None and s["mode"] >= 0]
    unresolved = [s for s in sites if s["mode"] is None]
    print(
        f"  scanned {scanned} word(s) in [0x{LOAD:08X}, 0x{TEXT_END:08X}); {len(sites)} direct jal "
        f"to 0x{shipping[ENTRY_NAME]:08X}"
    )
    print(
        f"    {len(queries)} query site(s) this tool NAMED from the call's delay slot or a "
        f"straight-line walk, {len(waits)} waiting call(s) NAMED, and {len(unresolved)} site(s) this "
        f"tool could NOT resolve and did not guess"
    )
    for site in sites:
        if site["mode"] is None:
            kind = "UNRESOLVED here"
        elif site["mode"] < 0:
            kind = f"query a0={site['mode']}"
        else:
            kind = f"WAIT a0={site['mode']}"
        print(f"    0x{site['addr']:08X}  {kind:18s} [{site['evidence']}]")
    if unresolved:
        print(
            f"    the {len(unresolved)} unresolved site(s) are resolved by Ghidra decompilation of "
            f"their enclosing functions, not by this tool"
        )

    if len(sites) != EXPECTED_TOTAL_SITES:
        problems.append(
            f"the image has {len(sites)} direct jal to the VSync entry, not the measured "
            f"{EXPECTED_TOTAL_SITES}; a new call site may wait, which a query counter "
            "does not answer"
        )
    if len(waits) != EXPECTED_WAIT_SITES or (
        waits and waits[0]["addr"] != EXPECTED_WAIT_SITE
    ):
        named = ", ".join(f"0x{w['addr']:08X}" for w in waits) or "none"
        problems.append(
            f"this tool named {len(waits)} waiting call(s) ({named}), not the measured "
            f"single one at 0x{EXPECTED_WAIT_SITE:08X}"
        )
    if tuple(sorted(s["addr"] for s in unresolved)) != tuple(
        sorted(DECOMPILED_RESIDUAL)
    ):
        got = ", ".join(f"0x{s['addr']:08X}" for s in unresolved) or "none"
        want = ", ".join(f"0x{a:08X}" for a in DECOMPILED_RESIDUAL)
        problems.append(
            f"the unresolved set changed: now [{got}], recorded [{want}]. A new "
            "unexamined call site is where a WAIT could hide, so it must be resolved and "
            "recorded here rather than left to be guessed"
        )
    if len(queries) + len(unresolved) != EXPECTED_QUERY_SITES:
        problems.append(
            f"{len(queries)} named + {len(unresolved)} decompiled query sites != the "
            f"measured {EXPECTED_QUERY_SITES}"
        )

    for name, measured in (
        (ENTRY_NAME, None),
        (BODY_END_NAME, VSYNC_BODY_END),
        (FIELD_COUNTER_NAME, measured_field),
    ):
        if name == ENTRY_NAME:
            # The entry is the anchor of the census, so it is confirmed by finding call sites rather
            # than by comparing it to itself.
            if not sites:
                problems.append(
                    "no call site reaches the declared VSync entry, so the census is "
                    "vacuous and the entry is unconfirmed"
                )
            continue
        if shipping[name] != measured:
            problems.append(
                f"SHIPPING {name} = 0x{shipping[name]:08X} but the image measures "
                f"0x{measured:08X}"
            )
    return problems


def selftest(exe: pathlib.Path) -> int:
    print("selftest: the cases that WOULD have failed, as permanent inputs")
    data = load_image(exe)
    header_text = HEADER_DEFAULT.read_text()

    failures = []

    # 1. The shipping comparison must REJECT a header whose field constant is wrong. Run the real
    #    check(), on a temporary copy — never by editing the live tree.
    perturbed = re.sub(
        rf"(\b{FIELD_COUNTER_NAME}\s*=\s*)0x[0-9A-Fa-f]{{8}}u",
        r"\g<1>0x8009AC6Cu",
        header_text,
    )
    if perturbed == header_text:
        failures.append(
            "could not build a perturbed header, so the rejection case never ran"
        )
    else:
        problems = check(data, perturbed)
        if not any("SHIPPING kFieldCounter" in p for p in problems):
            failures.append(
                "a header claiming 0x8009AC6C was ACCEPTED; this tool cannot detect a "
                "wrong shipping constant, which is the only thing it exists to detect"
            )
        else:
            print(
                "  ok  a header claiming 0x8009AC6C is REJECTED with the measured 0x8009AC68"
            )

    # 2. The discriminator for the census: perturb the declared entry so no call site reaches it.
    off_entry = re.sub(
        rf"(\b{ENTRY_NAME}\s*=\s*)0x[0-9A-Fa-f]{{8}}u", r"\g<1>0x800859A4u", header_text
    )
    problems = check(data, off_entry)
    if not any("no call site" in p for p in problems):
        failures.append(
            "a header whose VSync entry reaches no call site was ACCEPTED; the census "
            "would have reported a vacuous pass"
        )
    else:
        print(
            "  ok  a header whose VSync entry reaches no call site is REJECTED as vacuous"
        )

    # 3. The undeclared-constant case: a header with no kFieldCounter at all must refuse, not pass.
    stripped = re.sub(
        rf"^\s*inline constexpr std::uint32_t {FIELD_COUNTER_NAME}.*\n",
        "",
        header_text,
        flags=re.MULTILINE,
    )
    if stripped == header_text:
        failures.append(
            "could not strip the field constant, so the refusal case never ran"
        )
    else:
        try:
            parse_header(stripped)
            failures.append(
                "a header with no field-counter constant was ACCEPTED; an undeclared "
                "query counter reads as a pass when it is a refusal"
            )
        except Refusal:
            print(
                "  ok  a header with no field-counter constant is REFUSED, not passed"
            )

    # 4. Identity: a byte-perturbed image must refuse before it measures anything. The perturbation
    #    is applied in memory to a copy, so the provisioned image is never touched.
    mutated = bytearray(data)
    mutated[HEADER + (VSYNC_FIELD_LOAD - LOAD)] ^= 0x01
    try:
        check(bytes(mutated), header_text)
        failures.append(
            "a byte-perturbed image was measured instead of refused; the file offset is "
            "not actually pinned, so every reported address could be shifted"
        )
    except Refusal:
        print(
            "  ok  a byte-perturbed image is REFUSED by the ground-truth pin before it measures"
        )

    # 5. The real thing, once, so a selftest can never pass by never running the shipping path.
    problems = check(data, header_text)
    if problems:
        failures.append(
            "the unmodified shipping header does not match the image: "
            + "; ".join(problems)
        )
    else:
        print("  ok  the unmodified shipping header matches the image")

    if failures:
        for line in failures:
            print("  FAIL " + line)
        return 1
    print(
        "PASS: every rejection case above fired, and the shipping header matches the image."
    )
    return 0


def parse_args(argv: list[str]) -> tuple[pathlib.Path, pathlib.Path]:
    exe, header = EXE_DEFAULT, HEADER_DEFAULT
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag in ("--exe", "--header") and index + 1 >= len(argv):
            raise Refusal(f"{flag} needs a path")
        if flag == "--exe":
            exe = pathlib.Path(argv[index + 1])
            index += 2
        elif flag == "--header":
            header = pathlib.Path(argv[index + 1])
            index += 2
        else:
            index += 1  # --selftest and anything else is handled by the caller
    return exe, header


def main() -> int:
    try:
        exe, header = parse_args(sys.argv[1:])
        data = load_image(exe)
        if MANIFEST.is_file():
            expected = json.loads(MANIFEST.read_text()).get("sha256")
            actual = hashlib.sha256(data).hexdigest()
            if expected and actual != expected:
                raise Refusal(
                    f"{exe} hashes to {actual}; titles/tekken3/executable.json records "
                    f"{expected}. NOTHING WAS MEASURED."
                )
            print(
                f"identity: {exe.name} sha256 {actual} matches titles/tekken3/executable.json"
            )
        else:
            print(
                f"identity: REFUSED no manifest at {MANIFEST}; measuring {exe.name} unverified"
            )

        if "--selftest" in sys.argv:
            return selftest(exe)

        if not header.is_file():
            raise Refusal(
                f"no shipping header at {header}. This tool compares what the product SHIPS against "
                "what it measures, so a missing header is a refusal, not a pass."
            )
        problems = check(data, header.read_text())
    except Refusal as refusal:
        print(f"REFUSED: {refusal}")
        return 2

    if problems:
        for line in problems:
            print(f"PROBLEM: {line}")
        print(f"FAIL: {len(problems)} problem(s).")
        return 1
    print(
        "PASS: the shipping field counter, VSync entry and body end all match the authenticated "
        "image, the two measured writers touch that word, and the call-site census is the measured "
        "21 queries / 1 wait."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
