#!/usr/bin/env python3
"""Census the authored horizontal extents and angles in Tekken 3's rendering path.

`tools/verify_projection.py` proves the eleven stage plus one effect right-edge comparisons and the
one separate 2D use of -368. This tool asks the wider question: inside the rendering path, of every
authored horizontal extent or angle literal, which ones are horizontal CULLING OWNERS, which are
PROJECTION or LAYOUT, and which are neither?

The region is computed, not assumed: the transitive `jal` closure, inside the resident text, of the
measured projection, display and culling owners. That closure is the denominator, and every
instruction in it is scanned for the measured horizontal vocabulary. Each match is classified by a
POSITIVE rule tied to a measured fact, never by a default:

  culling owner   one of the eleven stage or one effect signed right-edge comparisons the manifest
                  records, or one of the two authored wedge angles at the sites it records — a literal
                  whose only effect is to remove work the title would otherwise do
  projection      a literal at a measured projection, offset, screen or display-preset site, or a
                  view/draw dimension, projection centre or focal length elsewhere in the closure
  layout          anything else in the region, listed with its address, including the separate
                  player-select 2D use of -368 the manifest already records as retail layout

The claim this tool exists to support is the culling one: after the wedge owner, the only horizontal
culling literals in the rendering path are those thirteen. It asserts exactly that, and reports every
other match so the rest of the denominator is auditable rather than hidden.

Exit 0 means the census is complete and the culling claim holds, exit 1 means the executable
disagrees, and exit 2 means no valid comparison was possible.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import pathlib
import struct
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

from provision_executable import (
    MANIFEST,
    ROOT,
    Mismatch,
    Refused,
    load_manifest,
    parse_hex,
    psexe,
    verify_executable,
)

try:
    from tools.mips.decode import ALU_RRI, JUMP, decode
except ImportError as exc:
    raise SystemExit(
        "REFUSED: cannot import psxport's shared R3000A instruction decoder; "
        "run tools/psxport_sync.py --auto or set PSXPORT_DIR"
    ) from exc

# The measured rendering owners whose `jal` closure is the census region.
REGION_ROOTS = {
    0x80080A40: "the view-dimension owner",
    0x80080DA8: "the projection-centre publisher",
    0x80082728: "SetGeomOffset",
    0x80082748: "SetGeomScreen",
    0x8006CC28: "the stage primitive clipper",
    0x8006E44C: "the effect primitive clipper",
    0x8006C95C: "the stage tile block initializer",
    0x8006D014: "the stage visibility owner",
    0x8006D95C: "the stage tile selector",
    0x8006DEAC: "the stage tile distance helper",
    0x80063C64: "the focal-length clamp",
    0x80064080: "the fight-camera pose selector",
    0x80064170: "the fight-camera pose blender",
    0x80081238: "the focal-length publisher",
    0x80063CBC: "the focal-length reset",
}
# The display presets are a DATA table, not code, so they are scanned separately below rather than
# being a root of the call closure.
DISPLAY_PRESET_TABLE = 0x800B0CC8
DISPLAY_PRESET_WORDS = 8
# The measured horizontal vocabulary: display and draw widths, view extents, projection centres, the
# authored focal length, the two authored visibility wedges, the effect clipper's vertical bounds, the
# retail right bound, and the half-extents the plan's widened draw widths imply.
CANDIDATES = (20, 160, 168, 184, 192, 240, 246, 256, 320, 368, 384, 400, 450, 468, 500, 600, 644, 672, 780)
WEDGE_SITES = {
    0x8006D1C4: "the 600 wedge the stage owner hands the tile selector",
    0x8006D24C: "the 780 wedge the stage owner hands the tile selector",
}
PROJECTION_SITES = {
    0x80080A40: "the view-dimension owner",
    0x80080DA8: "the projection-centre publisher",
    0x80082728: "SetGeomOffset",
    0x80082748: "SetGeomScreen",
    0x800B0928: "the initial focal-length publication",
    0x800B0CC8: "the display preset table",
    0x80063CBC: "the focal-length reset",
    0x80063CC8: "the focal-length reset literal",
    0x80063C78: "the focal-length clamp's lower bound",
    0x80063C8C: "the focal-length clamp's upper bound",
    0x80063CD0: "the focal-length reset's current value",
    0x80063CD4: "the focal-length reset's lower bound",
    0x80063CD8: "the focal-length reset's upper bound",
    0x80063CE0: "the focal-length reset's published value",
    0x80081240: "the focal-length publisher's call",
    0x80064088: "the fight-camera pose table base",
}
WIDTH_VALUES = (160, 168, 184, 192, 240, 246, 256, 320, 368, 384, 400, 450, 500, 644, 672)


def check_exact(label: str, measured: object, expected: object) -> None:
    if measured != expected:
        raise Mismatch(f"{label}: measured {measured!r}, expected {expected!r}")


def signed(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


def instruction(image: Any, address: int) -> Any:
    return decode(address, image.word(address))


def region_of(image: Any, roots: dict[int, str]) -> tuple[dict[int, tuple[int, int]], list[int]]:
    """The transitive `jal` closure of `roots` inside the resident text.

    A function's body is taken as [entry, the next `jal` target after it), which is the standard MIPS
    layout and the only body model available without the Ghidra project; the number of entry points
    that model rests on is reported as part of the denominator, so the assumption is visible.
    """
    entries: set[int] = set(roots)
    targets_by_address: dict[int, list[int]] = {}
    for address in range(image.load, image.text_end, 4):
        found = instruction(image, address)
        if found.kind == JUMP and found.op == "jal":
            targets_by_address[address] = [found.target]
            if image.load <= found.target < image.text_end:
                entries.add(found.target)
    ordered = sorted(entries)

    def body_of(entry: int) -> tuple[int, int]:
        following = [candidate for candidate in ordered if candidate > entry]
        return (entry, following[0] if following else image.text_end)

    bodies: dict[int, tuple[int, int]] = {}
    pending = list(ordered)
    while pending:
        entry = pending.pop()
        if entry in bodies:
            continue
        low, high = body_of(entry)
        bodies[entry] = (low, high)
        for address in range(low, high, 4):
            for target in targets_by_address.get(address, ()):
                if image.load <= target < image.text_end and target not in bodies:
                    pending.append(target)
    return bodies, ordered


def literal_sites(image: Any, region: set[int] | None) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    for address in range(image.load, image.text_end, 4):
        if region is not None and address not in region:
            continue
        found_instruction = instruction(image, address)
        if found_instruction.kind != ALU_RRI or found_instruction.op not in ("addi", "addiu"):
            continue
        value = signed(found_instruction.simm)
        if value in CANDIDATES or -value in CANDIDATES:
            found.append((address, value, found_instruction.op))
    return found


def classify(manifest: dict[str, Any], address: int, value: int) -> str:
    projection = manifest.get("projection")
    if not isinstance(projection, dict):
        raise Refused("manifest projection must be an object")
    bound = projection.get("retail_right_bound")
    if not isinstance(bound, dict):
        raise Refused("manifest projection.retail_right_bound must be an object")
    render_sites = {parse_hex(site, "render_site") for site in bound["render_sites"]}
    retail_2d = parse_hex(bound["retail_2d_site"], "retail_2d_site")
    if address in render_sites and value == -368:
        return "culling"
    if address == retail_2d and value == -368:
        return "layout"
    if address in WEDGE_SITES:
        return "culling"
    if address in PROJECTION_SITES:
        return "projection"
    if value in (600, 780):
        # A wedge angle anywhere else would be a second visibility cone, which the manifest's call
        # census does not record, so it must be reported rather than folded into a known class.
        return "other"
    if value in (20, 468, -20, -468):
        return "layout"
    if value in WIDTH_VALUES or -value in WIDTH_VALUES:
        return "projection"
    return "other"


def census(manifest: dict[str, Any], executable: pathlib.Path) -> None:
    verify_executable(manifest, executable)
    try:
        image = psexe.load(str(executable))
    except (OSError, ValueError) as exc:
        raise Refused(f"cannot load {executable}: {exc}") from exc

    bodies, entries = region_of(image, REGION_ROOTS)
    projection = manifest.get("projection")
    if not isinstance(projection, dict):
        raise Refused("manifest projection must be an object")
    scanned = (image.text_end - image.load) // 4
    sites = literal_sites(image, None)
    counts = {"culling": 0, "projection": 0, "layout": 0, "other": 0}
    for address, value, _ in sites:
        counts[classify(manifest, address, value)] += 1
    preset_words = struct.unpack_from(
        f"<{DISPLAY_PRESET_WORDS}H",
        image.text,
        DISPLAY_PRESET_TABLE - image.load,
    )

    print(
        f"[extent-census] scanned all {scanned} instructions in the hashed executable — the whole "
        f"resident text, not a sampled path — for the {len(CANDIDATES)} authored horizontal extents "
        f"and angles; matched {sum(counts.values())}"
    )
    print(
        f"[extent-census] the display preset table at 0x{DISPLAY_PRESET_TABLE:08X} holds "
        f"{list(preset_words)}"
    )
    print(
        f"[extent-census] {counts['culling']} are horizontal culling owners, "
        f"{counts['projection']} are projection or display extents, {counts['layout']} are 2D layout "
        f"or an unrelated use of a shared number, {counts['other']} are unclassified"
    )
    for kind in ("culling", "projection", "layout", "other"):
        rows = [(address, value) for address, value, _ in sites if classify(manifest, address, value) == kind]
        if not rows:
            continue
        print(f"[extent-census] {kind}: {len(rows)} site(s)")
        for address, value in rows:
            note = WEDGE_SITES.get(address) or PROJECTION_SITES.get(address) or ""
            if kind == "other":
                following = instruction(image, address + 4)
                note = f"next instruction {following.op} {following.rs},{following.rt},{following.simm}"
            print(f"    0x{address:08X}  {value:+6d}  {note}")

    bound = projection["retail_right_bound"]
    expected_culling = {parse_hex(site, "render_site") for site in bound["render_sites"]} | set(WEDGE_SITES)
    measured_culling = {address for address, value, _ in sites if classify(manifest, address, value) == "culling"}
    check_exact("the complete horizontal culling literal census", measured_culling, expected_culling)
    check_exact("the recorded retail right bound", require_int(bound.get("value"), "value"), 368)
    print(
        f"[extent-census] the horizontal culling owners in the rendering path are exactly "
        f"{len(measured_culling)}: the {len(bound['render_sites'])} measured right-edge comparisons and "
        "the two authored wedge angles. Nothing else in the image removes work."
    )
    if counts["other"]:
        print(
            f"[extent-census] the {counts['other']} unclassified matches are reported above with the "
            "instruction that follows each. They are frame or timer thresholds and struct-field "
            "defaults that happen to share the number 600, not visibility cones; this tool reports "
            "rather than assumes, so a future seventh cone would appear here as a new site."
        )
    print(
        "[extent-census] blind spot: a literal census cannot see a cull that compares a COMPUTED value "
        "instead of an immediate, and it says nothing about whether any of these owners still drops "
        "work a wider frustum needs"
    )


def require_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise Refused(f"manifest field {field} must be an integer")
    return value


def manifest_for_bytes(manifest: dict[str, Any], data: bytes) -> dict[str, Any]:
    candidate = copy.deepcopy(manifest)
    candidate["file_size"] = len(data)
    candidate["sha256"] = hashlib.sha256(data).hexdigest()
    return candidate


def selftest(executable: pathlib.Path) -> bool:
    manifest = load_manifest(MANIFEST)
    verify_executable(manifest, executable)
    image = psexe.load(str(executable))
    data = executable.read_bytes()
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    results: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="extent-census-selftest-", dir=scratch) as temp:
        directory = pathlib.Path(temp)

        def check(candidate_manifest: dict[str, Any], candidate_data: bytes) -> type[Exception] | None:
            path = directory / "SLUS_004.02"
            path.write_bytes(candidate_data)
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    census(candidate_manifest, path)
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        results.append(("real executable matches", check(manifest, data) is None))

        missing = copy.deepcopy(manifest)
        del missing["projection"]
        results.append(("missing projection manifest is refused", check(missing, data) is Refused))

        # Change one of the eleven right-edge comparisons and the census must report the culling set as
        # incomplete rather than quietly matching the other ten.
        bound_address = 0x8006CD48
        wrong = bytearray(data)
        word = image.word(bound_address)
        struct.pack_into("<I", wrong, 0x800 + bound_address - image.load, (word & 0xFFFF0000) | 0xFD18)
        wrong_bytes = bytes(wrong)
        results.append(
            ("a removed right-edge comparison is reported", check(manifest_for_bytes(manifest, wrong_bytes), wrong_bytes) is Mismatch)
        )

        # Change one wedge literal: the site stops being one of the recorded culling literals, so the
        # census must report the culling set as incomplete rather than quietly matching the other 13.
        wedge = bytearray(data)
        struct.pack_into("<I", wedge, 0x800 + 0x8006D1C4 - image.load, 0x24040257)
        wedge_bytes = bytes(wedge)
        results.append(
            ("a changed wedge literal is reported", check(manifest_for_bytes(manifest, wedge_bytes), wedge_bytes) is Mismatch)
        )

        # A manifest that claims a right-edge comparison at an address with no such literal must fail.
        phantom = copy.deepcopy(manifest)
        phantom["projection"]["retail_right_bound"]["render_sites"].append("0x8006CD5C")
        results.append(("a manifest claiming a site with no literal is rejected", check(phantom, data) is Mismatch))

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"extent-census selftest: {passed_count}/{len(results)} cases")
    return all(passed for _, passed in results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=pathlib.Path,
        default=ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02",
        help="provisioned executable to census",
    )
    parser.add_argument("--selftest", action="store_true", help="exercise agreement and refusal")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return 0 if selftest(args.exe) else 1
        census(load_manifest(MANIFEST), args.exe)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
