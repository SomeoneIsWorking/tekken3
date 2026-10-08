#!/usr/bin/env python3
"""Diffs game/fieldclock/field_clock.h against what the authenticated executable measures.

Addresses are decoded from instruction words, never transcribed. It also censuses the VSync call
sites: 21 of 22 are negative-mode queries and exactly one waits, which is what makes declaring the
query counter sufficient.

Usage:
    tools/verify_vsync_field_clock.py [--exe PATH] [--header PATH]
    tools/verify_vsync_field_clock.py --selftest [--exe PATH]

The selftest runs the shipping check() against perturbed copies of the header and image and requires
each to be rejected; the live tree is not edited.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "external/psxport"))

from tools.formats import psx_exe
from tools.mips.decode import decode

EXE_DEFAULT = ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
HEADER_DEFAULT = ROOT / "game" / "fieldclock" / "field_clock.h"
MANIFEST = ROOT / "titles" / "tekken3" / "executable.json"

# Three instructions from the Ghidra disassembly that all decode to 0x8009AC68; they pin the file offset.
GROUND_TRUTH = {
    0x80085A0C: 0x8C42AC68,  # lw v0, -0x5398(v0)  -- the negative-mode field read
    0x8008637C: 0xAC20AC68,  # sw zero, -0x5398(at) -- the library init zeroes the field word
    0x800863DC: 0xAC22AC68,  # sw v0, -0x5398(at)  -- the vblank callback increments it
}

# Anchor instruction addresses; the decoded values are cross-checks.
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

# Six sites set a0 behind a loop edge and stay unresolved here; Ghidra shows FUN_80083904,
# FUN_80083B84, FUN_800846D0, FUN_800910DC, FUN_80091254 and FUN_80091328 all pass -1. Any new
# unresolved site fails the gate.
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

FIELD_COUNTER_NAME = "kCounter"
ENTRY_NAME = "kEntry"
BODY_END_NAME = "kBodyEnd"


class Refusal(Exception):
    """Reported as a refusal, not an empty result; exits non-zero."""


def load_image(path: pathlib.Path) -> PsxExe:
    if not path.is_file():
        raise Refusal(
            f"no authenticated executable at {path}. Provision it first; this tool "
            "measures the image and will not answer from a remembered number."
        )
    try:
        image = psx_exe.load(path)
    except (OSError, ValueError) as error:
        raise Refusal(
            f"{path} is not a readable PS-X EXE: {error}. NOT MEASURED — this is a "
            "refusal, not an empty result."
        ) from error
    if MANIFEST.is_file():
        recorded = json.loads(MANIFEST.read_text()).get("file_size")
        if recorded is not None and path.stat().st_size != recorded:
            raise Refusal(
                f"{path} is {path.stat().st_size} byte(s); the manifest records "
                f"{recorded}. NOT MEASURED — this is a refusal, not an empty result."
            )
    return image


def word(image: psx_exe.PsxExe, addr: int) -> int:
    try:
        return image.word(addr)
    except IndexError:
        raise Refusal(f"0x{addr:08X} is outside the authenticated text") from None


def decode_at(image: psx_exe.PsxExe, addr: int):
    return decode(addr, word(image, addr))


def offset_problems(image: psx_exe.PsxExe) -> list[str]:
    problems = []
    for addr, expected in sorted(GROUND_TRUTH.items()):
        actual = word(image, addr)
        if actual != expected:
            problems.append(
                f"0x{addr:08X}: expected 0x{expected:08X}, read 0x{actual:08X}"
            )
    return problems


def measure_field_counter(image: psx_exe.PsxExe) -> int:
    """The word a negative VSync mode returns, computed from the instruction that reads it."""
    ins = decode_at(image, VSYNC_FIELD_LOAD)
    if ins.kind != "load" or ins.op != "lw":
        raise Refusal(
            f"0x{VSYNC_FIELD_LOAD:08X} is {ins.kind}/{ins.op}, not the expected lw; the "
            "negative-mode read was not found where the disassembly says it is"
        )
    lui = decode_at(image, VSYNC_FIELD_LOAD - 4)
    if lui.kind != "lui":
        raise Refusal(
            f"0x{VSYNC_FIELD_LOAD - 4:08X} is {lui.kind}, not the expected lui base"
        )
    base = (lui.imm << 16) & 0xFFFFFFFF
    return (base + ins.simm) & 0xFFFFFFFF


def measure_negative_arm_shape(image: psx_exe.PsxExe) -> list[str]:
    """Prove the field read is the negative arm's return: a signed test on a0, the waiting modes'
    return in its delay slot, the field load as fall-through, and a jump to the epilogue after it."""
    problems = []
    branch = decode_at(image, VSYNC_NEGATIVE_BRANCH)
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
    delay = decode_at(image, VSYNC_BRANCH_DELAY)
    if delay.kind != "alu_rri" or delay.op != "andi" or delay.imm != 0xFFFF:
        problems.append(
            f"0x{VSYNC_BRANCH_DELAY:08X} is {delay.kind}/{delay.op} imm={delay.imm}, not "
            "the andi 0xFFFF that forms the waiting modes' return value"
        )
    arm_delay = decode_at(image, VSYNC_FIELD_LOAD_DELAY)
    if arm_delay.kind != "jump" or arm_delay.op != "j":
        problems.append(
            f"0x{VSYNC_FIELD_LOAD_DELAY:08X} is {arm_delay.kind}/{arm_delay.op}, not the "
            "unconditional jump to the epilogue that returns the field word"
        )
    return problems


def measure_writers(image: psx_exe.PsxExe) -> list[tuple[int, int]]:
    """Every lui-base/lw-or-sw pair in the two known writers, decoded to the address it touches."""
    found = []
    for entry in (VSYNC_INIT_FIELD_STORE, VSYNC_CALLBACK_FIELD_STORE):
        store = decode_at(image, entry)
        if store.kind != "store":
            raise Refusal(
                f"0x{entry:08X} is {store.kind}/{store.op}, not the expected store"
            )
        base_ins = decode_at(image, entry - 4)
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


def census_vsync_calls(image: psx_exe.PsxExe, entry: int) -> tuple[list[dict], int]:
    """Every direct jal to the VSync entry, classified by the mode in a0.

    The mode comes from the call's delay slot or a straight-line walk back to the a0 write; crossing
    a branch leaves the site unresolved.
    """
    sites = []
    scanned = 0
    for addr in range(image.load, image.text_end, 4):
        raw = word(image, addr)
        scanned += 1
        if (raw >> 26) != 3:  # jal
            continue
        target = ((addr + 4) & 0xF0000000) | ((raw & 0x03FFFFFF) << 2)
        if target != entry:
            continue
        mode = None
        evidence = ""
        delay = decode_at(image, addr + 4)
        mode = literal_mode(delay)
        evidence = f"delay slot {delay.op} r{delay.rs},r{delay.rt},{delay.simm}"
        if mode is None and delay.op not in ("sw", "sh", "sb"):
            mode, evidence = resolve_by_walk(image, addr, 12)
        sites.append({"addr": addr, "mode": mode, "evidence": evidence})
    return sites, scanned


def resolve_by_walk(image: psx_exe.PsxExe, call: int, limit: int) -> tuple[int | None, str]:
    for back in range(4, 4 * (limit + 1), 4):
        addr = call - back
        try:
            ins = decode_at(image, addr)
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


def check(image: psx_exe.PsxExe, header_text: str) -> list[str]:
    """The shipping comparison; everything the tool asserts goes through here."""
    problems = offset_problems(image)
    if problems:
        # Refuse: nothing below ran.
        raise Refusal(
            "the file offset is not pinned, so every address below would be shifted and "
            "wrong: " + "; ".join(problems) + " — NOTHING WAS MEASURED"
        )

    measured_field = measure_field_counter(image)
    writers = measure_writers(image)
    shipping = parse_header(header_text)

    problems = measure_negative_arm_shape(image)
    for entry, touched in writers:
        if touched != measured_field:
            problems.append(
                f"the writer at 0x{entry:08X} touches 0x{touched:08X}, not the measured "
                f"field word 0x{measured_field:08X}"
            )
    sites, scanned = census_vsync_calls(image, shipping[ENTRY_NAME])
    queries = [s for s in sites if s["mode"] is not None and s["mode"] < 0]
    waits = [s for s in sites if s["mode"] is not None and s["mode"] >= 0]
    unresolved = [s for s in sites if s["mode"] is None]
    print(
        f"  scanned {scanned} word(s) in [0x{image.load:08X}, 0x{image.text_end:08X}); {len(sites)} direct jal "
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
            # Confirmed by finding call sites, not by comparing it to itself.
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

    # 1. A wrong field constant must be rejected.
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
        if not any("SHIPPING kCounter" in p for p in problems):
            failures.append(
                "a header claiming 0x8009AC6C was ACCEPTED; this tool cannot detect a "
                "wrong shipping constant, which is the only thing it exists to detect"
            )
        else:
            print(
                "  ok  a header claiming 0x8009AC6C is REJECTED with the measured 0x8009AC68"
            )

    # 2. An entry no call site reaches must be rejected.
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

    # 3. A header with no kCounter must refuse.
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

    # 4. A byte-perturbed in-memory image must refuse before measuring.
    offset = VSYNC_FIELD_LOAD - data.load
    mutated = bytearray(data.text)
    mutated[offset] ^= 0x01
    try:
        check(dataclasses.replace(data, text=bytes(mutated)), header_text)
        failures.append(
            "a byte-perturbed image was measured instead of refused; the file offset is "
            "not actually pinned, so every reported address could be shifted"
        )
    except Refusal:
        print(
            "  ok  a byte-perturbed image is REFUSED by the ground-truth pin before it measures"
        )

    # 5. The unmodified header must match.
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
        image = load_image(exe)
        if MANIFEST.is_file():
            expected = json.loads(MANIFEST.read_text()).get("sha256")
            actual = hashlib.sha256(exe.read_bytes()).hexdigest()
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
        problems = check(image, header.read_text())
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
