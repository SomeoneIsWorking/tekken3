#!/usr/bin/env python3
"""recover_runtime_handlers.py — where the 20 mode handlers actually come from, answered by census.

THE QUESTION. `docs/issues/0016` records that 11 of the 20 mode-dispatch targets sit at or above
0x800C0000, that the window 0x800C0000-0x80131000 holds 0 `jr $ra` and 0 `addiu $sp,$sp,-N` in the
authenticated executable, and concluded the handlers are "written at run time from disc-compressed
resources" and therefore recoverable only by reading a live process.

That conclusion is a HYPOTHESIS about provenance, and it is the load-bearing one: if the handlers are
not in the disc and not in RAM, there is nothing to recover and the mode-3 path is unreachable by
this route. So the tool answers it from bytes, with denominators, and it can say "absent" as well as
"present". It refuses rather than reporting a zero it did not measure.

THREE INDEPENDENT ROUTES TO THE SAME BYTES, so no route can be trusted alone:

  route A  the DISC. Read the mode table at 0x80010000, resolve the 20 `jal` stubs at
           0x80028C94+i*0x10, and take each handler's bytes straight out of the authenticated
           executable. This is ground truth for the 9 handlers that are in-disc code.
  route B  the RAM. Read the same addresses out of a `dumpram` capture of a live run and DIFF them
           against route A. Every differing word is something the running game wrote.
  route C  the LOADER. Mode 0's resource table at 0x800B8D58 is a stride-8 array of 127
           `{size, offset}` pairs, each offset pointing at a compressed payload INSIDE the
           executable, and each payload is the LZ form `tools/verify_decompressor_lightrec.py`
           already re-derived. Decompress all 127 offline and census each for MIPS code markers.
           This route needs no product run at all, which is the point: if the handlers are
           decompressible from the disc, the recovery does not have to wait for the game to boot.

ARMS, so a uniform result is a warning rather than a confirmation:

  arm=indisc     the control that can fail: route B must reproduce route A byte for byte at the
                 9 in-disc handlers. If it does not, route B is not a faithful read of guest RAM
                 and every "absent" it reports is meaningless. Reported as N of 9 equal.
  arm=window     the subject: for each of the 11 handlers at or above 0x800C0000, how many MIPS
                 code markers does route A find, and how many does route B add. A uniform 0 is
                 reported as a zero WITH ITS DENOMINATOR, never as a bare "not found".
  arm=negative   a capture whose window was never written must report 0 present of 11. This arm is
                 what makes "0 present" mean "the game has not written it" instead of "the tool
                 cannot see it".
  arm=payload    route C: how many of the 127 decompressed images contain code markers, and does any
                 of them decode with a prologue at a window handler's address.
  arm=loaders    WHO can write those handlers. Every call site of the LZ decompressor and of the
                 placement pair, over the whole authenticated text, with the opcode histogram as
                 the denominator. This exists because `arm=payload` measured 0 of 127 code images
                 in mode 0's table, and "mode 0 is the only loader" is the belief that would have
                 made that a dead end instead of a measurement.

Usage:
  tools/recover_runtime_handlers.py --selftest
  tools/recover_runtime_handlers.py [--ram PATH] [--capture-field N]
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from provision_executable import (
    Mismatch,
    Refused,
    load_manifest,
    verify_executable,
)

LOAD = 0x80010000
RAM_BASE = 0x80000000
MODE_TABLE = 0x80010000
MODE_COUNT = 20
STUB_BASE = 0x80028C94
STUB_STRIDE = 0x10
WINDOW = 0x800C0000
TEXT_END = 0x80131000
# Mode 0's resource table: a count word then 127 stride-8 `{size, offset}` pairs, each offset
# relative to the table base and pointing at an LZ payload inside the executable.
RESOURCE_TABLE = 0x800B8D58
# The decompressed staging base mode 0 hands to the placer, and the placement cursor's global.
STAGING_BASE = 0x8012867C
PLACEMENT_CURSOR = 0x800A3B88

# Code markers, and the DENSITIES they must be judged against. A bare zero means nothing without
# the comparison, so every marker is reported next to the same marker's rate in the in-disc text,
# which is the reference corpus with a known answer.
PROLOGUE = re.compile(r"^27BD")  # addiu $sp,$sp,-N
RETURN = 0x03E00008  # jr $ra
# One image of the loader's decompressed stream is bounded by the guest wrapper's own 0x8240 test
# at 0x8004CAA0, so a decompressed image larger than that is a decode that ran away, not a big image.
MAX_IMAGE_BYTES = 0x8240


def manifest_path() -> pathlib.Path:
    """The provisioned executable this repository ships as runtime data, resolved from the same
    manifest the other tools use, so `verify_executable` can check its 8 identity/header facts."""
    path = ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
    if not path.is_file():
        raise Refused(
            f"the authenticated executable is not provisioned at {path}; run "
            f"tools/provision_executable.py first. An absent image is a refusal, not a zero."
        )
    return path


def opcode_histogram(blob: bytes) -> dict[int, int]:
    counts: dict[int, int] = {}
    for offset in range(0, len(blob) - 3, 4):
        counts[int.from_bytes(blob[offset : offset + 4], "little") & 0x3F] = (
            counts.get(int.from_bytes(blob[offset : offset + 4], "little") & 0x3F, 0)
            + 1
        )
    return counts


def code_markers(blob: bytes) -> tuple[int, int, int]:
    """(prologues, `jr $ra`, words scanned) for a word-aligned blob."""
    words = prologues = returns = 0
    for offset in range(0, len(blob) - 3, 4):
        words += 1
        word = int.from_bytes(blob[offset : offset + 4], "little")
        if PROLOGUE.match(f"{word:08X}"):
            prologues += 1
        if word == RETURN:
            returns += 1
    return prologues, returns, words


def entropy(counts: dict[int, int]) -> float:
    import math

    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


class Disc:
    """The authenticated executable's loaded text, addressed by guest virtual address."""

    def __init__(self, image: bytes) -> None:
        self.text = image[0x800:]

    def word(self, address: int) -> int:
        offset = address - LOAD
        return int.from_bytes(self.text[offset : offset + 4], "little")

    def bytes(self, address: int, count: int) -> bytes:
        offset = address - LOAD
        return self.text[offset : offset + count]


class Ram:
    """A `dumpram` capture: 2 MB of guest RAM at 0x80000000."""

    def __init__(self, blob: bytes, path: pathlib.Path) -> None:
        if len(blob) != 0x200000:
            raise Refused(
                f"RAM capture {path} is {len(blob)} bytes; a guest main-RAM dump is exactly "
                f"0x200000 (2097152). A short read is a failed capture, not an empty RAM."
            )
        self.blob = bytes(blob) if isinstance(blob, bytes) else blob
        self.path = path

    def word(self, address: int) -> int:
        offset = address - RAM_BASE
        if not 0 <= offset <= len(self.blob) - 4:
            raise Refused(f"address 0x{address:08X} is outside the captured guest RAM")
        return int.from_bytes(self.blob[offset : offset + 4], "little")

    def bytes(self, address: int, count: int) -> bytes:
        offset = address - RAM_BASE
        if not 0 <= offset <= len(self.blob) - count:
            raise Refused(
                f"address 0x{address:08X}+{count} is outside the captured guest RAM"
            )
        return self.blob[offset : offset + count]


def lz_decode(source: bytes, max_output: int) -> bytes:
    """The LZ form `tools/verify_decompressor_lightrec.py` re-derived from FUN_80031BFC.

    Re-implemented here rather than imported so this tool stands alone, and it is checked against
    that tool's own `reference_decode` in the selftest, so the two copies cannot drift silently.
    """
    cursor = 0
    output = bytearray()
    while cursor < len(source):
        control = source[cursor]
        cursor += 1
        if control == 0:
            return bytes(output)
        while control > 1:
            if control & 1:
                if cursor >= len(source):
                    raise Refused("literal exceeds the mapped payload")
                output.append(source[cursor])
                cursor += 1
            else:
                if cursor + 2 > len(source):
                    raise Refused("back-reference exceeds the mapped payload")
                token = (source[cursor] << 8) | source[cursor + 1]
                cursor += 2
                length = (token >> 11) or 32
                distance = (token & 0x7FF) or 2048
                if distance > len(output):
                    raise Refused("back-reference precedes the output start")
                if len(output) + length > max_output:
                    raise Refused(
                        f"image exceeds the guest wrapper's own 0x{max_output:X} bound at 0x8004CAA0"
                    )
                for _ in range(length):
                    output.append(output[-distance])
            if len(output) > max_output:
                raise Refused(
                    f"image exceeds the guest wrapper's own 0x{max_output:X} bound"
                )
            control >>= 1
    raise Refused(f"no LZ terminator in {len(source)} mapped payload bytes")


def mode_handlers(disc: Disc) -> list[tuple[int, int]]:
    """(mode, handler) for all 20 dispatch targets, resolved from the two disc facts.

    The table at MODE_TABLE holds a stub address per mode; each stub is a `jal` into the handler
    followed by the shared `j MODE_TAIL`. Both are read here rather than taken from a constant, so a
    wrong table base shifts every address and the tool says so instead of returning a confident
    non-zero answer.
    """
    handlers = []
    for mode in range(MODE_COUNT):
        stub = disc.word(MODE_TABLE + 4 * mode)
        jal = disc.word(stub)
        if jal >> 26 != 3:  # op == JAL
            raise Refused(
                f"mode {mode}: the dispatch table entry 0x{stub:08X} does not hold a `jal` "
                f"(0x{jal:08X}); the table base {MODE_TABLE:#010x} is wrong for this image."
            )
        target = ((jal & 0x03FFFFFF) << 2) | ((stub + 4) & 0xF0000000)
        handlers.append((mode, target))
    return handlers


def resource_table(disc: Disc) -> tuple[int, list[tuple[int, int]]]:
    count = disc.word(RESOURCE_TABLE)
    if count == 0 or count > 4096:
        raise Refused(
            f"the resource table's first word is {count}; expected a plausible entry count. "
            f"RESOURCE_TABLE {RESOURCE_TABLE:#010x} is wrong for this image."
        )
    entries = []
    for index in range(count):
        size = disc.word(RESOURCE_TABLE + 8 * index + 4)
        entries.append((disc.word(RESOURCE_TABLE + 8 * index), size))
    return count, entries


def report_indisc_control(disc: Disc, ram: Ram | None, handlers) -> tuple[int, int]:
    """arm=indisc. The control that can fail: RAM must equal the disc at every in-disc handler."""
    in_disc = [(m, a) for m, a in handlers if a < WINDOW]
    if not in_disc:
        raise Refused(
            "no handler resolved below the window; nothing to control against"
        )
    if ram is None:
        return 0, len(in_disc)
    equal = 0
    for _, address in in_disc:
        span = 0x400
        if disc.bytes(address, span) == ram.bytes(address, span):
            equal += 1
    return equal, len(in_disc)


def report_window(disc: Disc, ram: Ram | None, handlers) -> list[str]:
    """arm=window. Per handler: what the disc holds, and what the run added."""
    lines = []
    reference_pro, reference_ret, reference_words = code_markers(
        disc.bytes(0x80010000, 0xA0000)
    )
    lines.append(
        f"  reference corpus, the in-disc text 0x80010000-0x800B0000: {reference_words} words, "
        f"{reference_pro} prologues ({100.0 * reference_pro / reference_words:.2f}%), "
        f"{reference_ret} `jr $ra` ({100.0 * reference_ret / reference_words:.3f}%), "
        f"opcode entropy {entropy(opcode_histogram(disc.bytes(0x80010000, 0xA0000))):.3f} of 6.000"
    )
    window_pro, window_ret, window_words = code_markers(
        disc.bytes(WINDOW, TEXT_END - WINDOW)
    )
    lines.append(
        f"  the disc's own window 0x{WINDOW:08X}-0x{TEXT_END:08X}: {window_words} words, "
        f"{window_pro} prologues, {window_ret} `jr $ra`, "
        f"opcode entropy {entropy(opcode_histogram(disc.bytes(WINDOW, TEXT_END - WINDOW))):.3f}"
        f"  <- a uniform zero next to a 1% reference is a DECODED ABSENCE, not a scan that found nothing"
    )
    lines.append("")
    lines.append(
        "  mode  handler      class    disc:pro/jr   ram:pro/jr  ram diff words/1024  first word"
    )
    for mode, address in handlers:
        span = 0x400
        disc_blob = disc.bytes(address, span)
        d_pro, d_ret, _ = code_markers(disc_blob)
        if ram is None:
            r_pro = r_ret = -1
            differing = -1
            first = int.from_bytes(disc_blob[:4], "little")
        else:
            ram_blob = ram.bytes(address, span)
            r_pro, r_ret, _ = code_markers(ram_blob)
            differing = sum(
                1
                for i in range(0, span, 4)
                if disc_blob[i : i + 4] != ram_blob[i : i + 4]
            )
            first = int.from_bytes(ram_blob[:4], "little")
        klass = "window" if address >= WINDOW else "in-disc"
        lines.append(
            f"  {mode:4d}  0x{address:08X}  {klass:>7}  {d_pro:5d}/{d_ret:<5d}  "
            f"{r_pro:5d}/{r_ret:<5d}  {differing:5d}/{span // 4:<14d} 0x{first:08X}"
        )
    return lines


def report_negative(disc: Disc) -> str:
    """arm=negative. A RAM built from the disc alone must report the window unwritten."""
    ram = Ram(bytearray(b"\x00" * 0x200000), pathlib.Path("<synthetic: all zero>"))
    # Overwrite only the loaded text from the disc, so the synthetic capture is "the disc, and
    # nothing else" -- the state a run reaches before the loader has written anything.
    for address in range(LOAD, TEXT_END, 4):
        blob = disc.bytes(address, 4)
        ram.blob[address - RAM_BASE : address - RAM_BASE + 4] = blob
    equal, total = report_indisc_control(disc, ram, mode_handlers(disc))
    _, _, words = code_markers(ram.bytes(WINDOW, TEXT_END - WINDOW))
    pro, ret, _ = code_markers(ram.bytes(WINDOW, TEXT_END - WINDOW))
    return (
        f"  arm=negative (a capture holding the disc and nothing else): in-disc control "
        f"{equal}/{total} byte-identical, and the window holds {pro} prologues / {ret} `jr $ra` "
        f"in {words} words -- the same as the disc's own window, which is what makes a later "
        f"non-zero a real change rather than the tool's own noise."
    )


def report_payloads(disc: Disc) -> list[str]:
    """arm=payload. Decompress all of mode 0's resources offline and census each for code."""
    count, entries = resource_table(disc)
    header = (
        f"  the resource table at 0x{RESOURCE_TABLE:08X} declares {count} entries; the payload "
        f"for entry i is LZ at table_base + entries[i].offset"
    )
    lines = [header]
    code_images = []
    decoded = refused = 0
    for index, (_, offset) in enumerate(entries):
        source = RESOURCE_TABLE + offset
        if source < LOAD or source >= TEXT_END:
            refused += 1
            continue
        try:
            blob = lz_decode(disc.bytes(source, TEXT_END - source), MAX_IMAGE_BYTES)
        except Refused:
            refused += 1
            continue
        decoded += 1
        pro, ret, words = code_markers(blob)
        if pro or ret:
            code_images.append((index, source, words, pro, ret))
    lines.append(
        f"  decoded {decoded} of {count} payloads; {refused} refused (out of range, no terminator "
        f"inside the mapped text, or over the guest's own 0x{MAX_IMAGE_BYTES:X} image bound)"
    )
    lines.append(
        f"  images containing a code marker: {len(code_images)} of {decoded} decoded"
    )
    for index, source, words, pro, ret in code_images:
        lines.append(
            f"    entry {index:3d} at 0x{source:08X}: {words:5d} words, {pro:4d} prologues, "
            f"{ret:4d} `jr $ra`"
        )
    return lines


# The primitives whose call sites say which routine decompresses and places an image. Mode 0's
# loader is ONE of several; naming the others is the next measurement, not a guess.
LOADER_PRIMITIVES = {
    0x80031BFC: "FUN_80031BFC  LZ decompress (FUN_80031BFC's body matches the token layout "
    "tools/verify_decompressor_lightrec.py re-derived)",
    0x8007EFC8: "FUN_8007EFC8  placement-begin: *(0x800A3B88) = staging base",
    0x8007EFD8: "FUN_8007EFD8  placement-next: decode one image, advance the cursor",
    0x8004CA40: "FUN_8004CA40  mode 0's 127-resource load",
}


def opcode_histogram_top(blob: bytes, count: int, top: int = 8) -> str:
    counts: dict[int, int] = {}
    for offset in range(0, len(blob) - 3, 4):
        top = int.from_bytes(blob[offset : offset + 4], "little") >> 26
        counts[top] = counts.get(top, 0) + 1
    return " ".join(
        f"0x{k:02X}:{100.0 * v / count:.2f}%"
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:top]
    )


def scan_loader_call_sites(
    disc: Disc,
) -> tuple[dict[int, list[int]], int, dict[int, int]]:
    """Every `jal` to a loader primitive, with the opcode histogram as the denominator.

    THE OPCODE IS THE TOP SIX BITS. Two drafts of this census used `word & 0x3F`, which is the
    SPECIAL funct field, and reported 0 call sites and 0 `lui 0x800B` for a text that contains
    2,470 of the latter -- a uniform zero that read exactly like a result. The selftest pins the
    correction by requiring a `jal` to a known-present target to be found, so a census that cannot
    find what is there cannot be trusted to report what is absent.
    """
    text = disc.bytes(LOAD, TEXT_END - LOAD)
    words = len(text) // 4
    histogram: dict[int, int] = {}
    sites: dict[int, list[int]] = {target: [] for target in LOADER_PRIMITIVES}
    for index in range(words):
        raw = int.from_bytes(text[index * 4 : index * 4 + 4], "little")
        top = raw >> 26
        histogram[top] = histogram.get(top, 0) + 1
        if top != 0x03:  # JAL
            continue
        address = LOAD + index * 4
        target = ((raw & 0x03FFFFFF) << 2) | ((address + 4) & 0xF0000000)
        if target in sites:
            sites[target].append(address)
    return sites, words, histogram


def report_loaders(disc: Disc) -> list[str]:
    sites, words, _histogram = scan_loader_call_sites(disc)
    histogram_line = (
        f"  {words} words of the authenticated text scanned; opcode histogram "
        f"(top six bits, top 8) {opcode_histogram_top(disc.bytes(LOAD, TEXT_END - LOAD), words, 8)}"
    )
    lines = [histogram_line]
    lines.append("")
    for target, name in LOADER_PRIMITIVES.items():
        found = sites[target]
        lines.append(f"  0x{target:08X}  {len(found):3d} call site(s)  {name}")
        for address in found:
            lines.append(f"        0x{address:08X}")
    # A placer is a ROUTINE, and every `placement-begin` site is followed by its own
    # `placement-next` a few instructions later, so the count is the begin sites, not both.
    placers = sites[0x8007EFC8]
    unpaired = [
        a
        for a in placers
        if not any(n - a in range(1, 0x40) for n in sites[0x8007EFD8])
    ]
    lines.append("")
    lines.append(
        f"  {len(placers)} placement site(s), every one of them inside a routine that also calls "
        f"placement-next ({len(placers) - len(unpaired)}/{len(placers)} paired within 0x40 bytes). "
        f"So mode 0's loader is 1 of {len(placers)}, and the others are where a CODE image would "
        f"have to come from. Naming which of them runs is the next measurement; this tool does not "
        f"guess, and it does not treat mode 0's table as the whole loader set."
    )
    return lines


def selftest() -> int:
    """Show the instrument giving the OTHER answer, on a fixture where the answer is known."""
    checks = 0
    manifest = load_manifest()
    try:
        image = verify_executable(manifest, manifest_path())
    except (Refused, Mismatch) as error:
        print(f"[recover] REFUSED: {error}")
        return 1
    disc = Disc(image)
    handlers = mode_handlers(disc)

    # 1. The control can FAIL: corrupt one word of a capture and the in-disc arm must drop.
    equal, total = report_indisc_control(disc, None, handlers)
    if total != 9:
        raise AssertionError(f"expected 9 in-disc handlers, resolved {total}")
    checks += 1
    good = Ram(bytearray(b"\x00" * 0x200000), pathlib.Path("<selftest: disc-only>"))
    for address in range(LOAD, TEXT_END, 4):
        blob = disc.bytes(address, 4)
        good.blob[address - RAM_BASE : address - RAM_BASE + 4] = blob
    equal, _ = report_indisc_control(disc, good, handlers)
    if equal != total:
        raise AssertionError(
            f"a disc-only capture scored {equal}/{total} on the in-disc control"
        )
    checks += 1
    broken = Ram(bytearray(good.blob), pathlib.Path("<selftest: one word edited>"))
    broken.blob[0x80052CC4 - RAM_BASE] ^= 0x01
    equal_broken, _ = report_indisc_control(disc, broken, handlers)
    if equal_broken != total - 1:
        raise AssertionError(
            f"a one-word edit changed the in-disc control by {total - equal_broken}, expected 1; "
            f"the control cannot detect a clobbered capture"
        )
    checks += 1

    # 2. A zero-length capture is REFUSED, not reported as "0 of 0".
    try:
        Ram(b"\x00" * 0x1000, pathlib.Path("<selftest: truncated>"))
    except Refused:
        checks += 1
    else:
        raise AssertionError("a truncated RAM capture was accepted")

    # 3. A wrong table base is REFUSED, not silently producing 20 wrong handlers.
    for bad_base in (MODE_TABLE + 4, MODE_TABLE + 0x8000):
        try:
            for mode in range(MODE_COUNT):
                stub = disc.word(bad_base + 4 * mode)
                jal = disc.word(stub)
                if jal >> 26 != 3:
                    raise Refused("not a jal")
        except (Refused, IndexError):
            checks += 1
        else:
            if bad_base != MODE_TABLE:
                raise AssertionError(
                    f"table base {bad_base:#010x} produced a clean census"
                )

    # 4. The LZ decoder here agrees with the tool that re-derived it from the guest.
    sys.path.insert(0, str(ROOT / "tools"))
    import verify_decompressor_lightrec as reference

    _, expected = reference.reference_decode(image)
    mine = lz_decode(
        disc.bytes(0x800BAFCC, 0x121000 - 0xBAFCC + 0x80010000 - 0x80010000),
        MAX_IMAGE_BYTES,
    )
    if mine != expected:
        raise AssertionError(
            f"this tool's LZ decoder and verify_decompressor_lightrec's disagree: "
            f"{len(mine)} vs {len(expected)} bytes"
        )
    checks += 1

    # 5. The decoder can give the OTHER answer: a truncated payload must refuse, not return short.
    try:
        lz_decode(disc.bytes(0x800BAFCC, 4), MAX_IMAGE_BYTES)
    except Refused:
        checks += 1
    else:
        raise AssertionError("a 4-byte payload decoded instead of refusing")

    # 6. The code-marker census can give the OTHER answer: a blob of real code must score high and
    #    the same length of zeros must score zero. A census that cannot separate them measures
    #    nothing, and a uniform "0 in the window" would then be uninterpretable.
    # 1 KiB from mode 2's handler, 0x8004FA60: a function this repository has already read
    # instruction by instruction in docs/issues/0016, so "this is code" is not an assumption here.
    good_blob = disc.bytes(0x8004FA60, 0x1000)
    if code_markers(good_blob)[0] == 0:
        raise AssertionError("1 KiB of real code scored zero prologues")
    if code_markers(b"\x00" * 0x1000) != (0, 0, 1024):
        raise AssertionError("1 KiB of zeros did not score (0, 0, 1024)")
    checks += 2

    # 7. The call-site census must FIND a `jal` that is known to be there. This is the check that
    #    two drafts of it failed: they took the opcode from the low six bits, which is the SPECIAL
    #    funct field, and reported zero call sites and zero `lui 0x800B` for a text that holds
    #    2,470 of the latter. A uniform zero from a mis-slaced field is indistinguishable from a
    #    result unless the instrument is required to find something first.
    sites, words, histogram = scan_loader_call_sites(disc)
    if 0x800B0744 not in sites[0x8004CA40]:
        raise AssertionError(
            "the call-site census did not find mode 0's own loader call at 0x800B0744, so it cannot "
            "be used to report that some OTHER loader is absent"
        )
    if not any(sites[target] for target in LOADER_PRIMITIVES):
        raise AssertionError("the call-site census found no loader primitive at all")
    if words < 0x10000 or len(histogram) < 8:
        raise AssertionError(
            f"the opcode histogram has {len(histogram)} distinct opcodes over {words} words; a "
            f"census whose field is the wrong six bits collapses to a handful"
        )
    checks += 3

    print(
        f"[recover] selftest passed: {checks} checks, including a defeated in-disc control, a "
        f"truncated-capture refusal, two wrong-table-base refusals, an LZ cross-check against "
        f"verify_decompressor_lightrec, a short-payload refusal, a code census shown to "
        f"separate real code from zeros, and a call-site census required to FIND mode 0's own "
        f"loader call before it is allowed to report anything about the others"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument(
        "--ram",
        type=pathlib.Path,
        help="a `dumpram` capture of a live run (2,097,152 bytes)",
    )
    parser.add_argument(
        "--capture-field",
        type=int,
        default=0,
        help="the presented-field number the capture was taken at, for the record",
    )
    args = parser.parse_args()
    if args.selftest:
        return selftest()

    manifest = load_manifest()
    try:
        disc = Disc(verify_executable(manifest, manifest_path()))
        handlers = mode_handlers(disc)
        ram = Ram(args.ram.read_bytes(), args.ram) if args.ram else None
    except (Refused, Mismatch, OSError) as error:
        print(f"[recover] REFUSED: {error}")
        return 1

    print(
        f"[recover] image pinned; {MODE_COUNT} mode targets resolved from the dispatch table at "
        f"0x{MODE_TABLE:08X} and the `jal` stubs at 0x{STUB_BASE:08X}+i*{STUB_STRIDE:#x}"
    )
    if ram is None:
        print(
            "[recover] no --ram capture given: route B is not exercised and every RAM column is "
            "reported as NOT MEASURED, not as zero"
        )
    else:
        print(
            f"[recover] route B: {args.ram} ({ram.blob.__len__()} bytes"
            + (
                f", captured at presented field {args.capture_field}"
                if args.capture_field
                else ""
            )
            + ")"
        )
    print()

    print(
        "arm=indisc -- the control that can fail: the capture must equal the disc in-disc"
    )
    equal, total = report_indisc_control(disc, ram, handlers)
    if ram is None:
        print(
            f"  NOT MEASURED: no capture, so 0 of {total} compared. A control that did not run "
            f"is not a control that passed."
        )
    else:
        print(
            f"  {equal} of {total} in-disc handler(s) byte-identical to the disc over 1024 bytes each"
        )
        if equal != total:
            print(
                "  REFUSED: the capture disagrees with the authenticated image at a handler that "
                "is in-disc code, so it is not a faithful read of guest RAM and nothing below "
                "can be concluded from it."
            )
            return 1
    print()

    print(
        "arm=window -- the subject: what is at the 11 handlers at or above the window"
    )
    for line in report_window(disc, ram, handlers):
        print(line)
    print()

    print("arm=negative -- a capture holding the disc and nothing else")
    print(report_negative(disc))
    print()

    print(
        "arm=payload -- mode 0's resources, decompressed from the disc with no product run"
    )
    for line in report_payloads(disc):
        print(line)
    print()

    print("arm=loaders -- who else in this text can decompress and place an image")
    for line in report_loaders(disc):
        print(line)

    if ram is not None:
        print()
        print("the placement state in the capture, read from the guest's own globals")
        print(
            f"  *(0x{PLACEMENT_CURSOR:08X}) placement cursor = 0x{ram.word(PLACEMENT_CURSOR):08X}, "
            f"staging base 0x{STAGING_BASE:08X} -> "
            f"0x{ram.word(PLACEMENT_CURSOR) - STAGING_BASE:X} bytes consumed"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
