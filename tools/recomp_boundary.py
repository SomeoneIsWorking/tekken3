#!/usr/bin/env python3
"""Compare Tekken's generated startup slices with the independent CPU oracle.

The port executes the verified entry-to-main window in psxport's interpreter, then executes C
emitted by the shipping recompiler through ``game_main``'s first initializer return and the next
initializer call. The true-oracle leg executes the entire window in vendored Mednafen. No later
game code, BIOS, device result, or whole-image seed set is guessed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import pathlib
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from boot_oracle import (
    REGISTER_NAMES,
    BoundaryState,
    check_tool,
    compare_states,
    parse_psxport,
    run_process,
)
from provision_executable import MANIFEST, Mismatch, Refused, load_manifest, parse_hex
from verify_startup import startup_fields, verify_startup

PSXPORT = pathlib.Path(os.environ.get("PSXPORT_DIR", ROOT / "external" / "psxport"))
RECOMPILER_DIR = PSXPORT / "tools" / "recomp"
DEFAULT_EXE = ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02"
DEFAULT_GENERATED = ROOT / "generated"
DEFAULT_BUILD = ROOT / "build"
DEFAULT_RAW = ROOT / "scratch" / "raw" / "t3-04"
SOURCE = "boundary_slices.c"
METADATA = "boundary_slices.json"
TRACE_RE = re.compile(
    r"^(?P<step>\d+) 0x(?P<pc>[0-9A-Fa-f]{8}) (?P<cycles>\d+)(?P<changes>.*)$"
)
INITIAL_RE = re.compile(
    r"^# initial: pc=0x(?P<pc>[0-9A-Fa-f]+) "
    r"gp=0x(?P<gp>[0-9A-Fa-f]+) sp=0x(?P<sp>[0-9A-Fa-f]+)$",
    re.MULTILINE,
)
CHANGE_RE = re.compile(r"\b(?P<name>[a-z0-9]+)=0x(?P<value>[0-9A-Fa-f]+)")


@dataclass(frozen=True)
class GeneratedSlices:
    start: int
    first_call_address: int
    initializer_start: int
    initializer_end: int
    return_boundary: int
    next_call_address: int
    next_target: int
    next_end: int
    first_instructions: int
    initializer_instructions: int
    next_instructions: int
    emitter_version: str
    source: str


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_recompiler():
    if not (RECOMPILER_DIR / "emit.py").is_file():
        raise Refused(f"shipping recompiler is absent: {RECOMPILER_DIR / 'emit.py'}")
    sys.path.insert(0, str(RECOMPILER_DIR))
    try:
        return importlib.import_module("emit"), importlib.import_module("psexe")
    except (ImportError, OSError) as exc:
        raise Refused(f"cannot load the shipping recompiler: {exc}") from exc


def render_slices(executable: pathlib.Path) -> GeneratedSlices:
    manifest = load_manifest(MANIFEST)
    verify_startup(manifest, executable)
    fields = startup_fields(manifest)
    start = int(fields["call_target"])
    first_call_address = int(fields["main_call_address"])
    initializer_start = int(fields["main_call_target"])
    initializer_end = int(fields["initializer_end"])
    return_boundary = first_call_address + 8
    next_call_address = int(fields["next_call_address"])
    next_target = int(fields["next_call_target"])
    next_end = next_call_address + 8
    first_instructions = (return_boundary - start) // 4
    initializer_instructions = (initializer_end - initializer_start) // 4
    next_instructions = (next_end - next_call_address) // 4
    if first_instructions <= 0 or return_boundary - start != first_instructions * 4:
        raise Refused("measured game_main prefix is not a non-empty aligned instruction range")
    if (
        initializer_instructions <= 0
        or initializer_end - initializer_start != initializer_instructions * 4
    ):
        raise Refused("measured first initializer is not a non-empty aligned instruction range")
    if next_instructions != 2 or next_call_address != return_boundary:
        raise Refused("measured next initializer call is not the immediate two-instruction slice")

    emitter, psexe = load_recompiler()
    image = psexe.load(str(executable))
    initializer_body: list[str] = []
    emitter.emit_func(
        image,
        initializer_start,
        initializer_end,
        {start, initializer_start, next_target},
        initializer_body,
        "tekken3_first_initializer_body",
        emitter.MAIN_NAMES,
    )
    first_body: list[str] = []
    emitter.emit_func(
        image,
        start,
        return_boundary,
        {start, initializer_start, next_target},
        first_body,
        "tekken3_main_first_initializer",
        emitter.MAIN_NAMES,
    )
    next_body: list[str] = []
    emitter.emit_func(
        image,
        next_call_address,
        next_end,
        {start, initializer_start, next_target},
        next_body,
        "tekken3_main_next_initializer_call",
        emitter.MAIN_NAMES,
    )
    source = "\n".join(
        (
            "// GENERATED by psxport tools/recomp/emit.py — DO NOT EDIT.",
            '#include "core.h"',
            "void tekken3_boundary_hook(Core*, uint32_t);",
            "",
            *initializer_body,
            "",
            f"void func_{initializer_start:08X}(Core* c) {{",
            f"  tekken3_boundary_hook(c, 0x{initializer_start:08X}u);",
            "  tekken3_first_initializer_body(c);",
            "}",
            "",
            f"void func_{next_target:08X}(Core* c) {{",
            f"  tekken3_boundary_hook(c, 0x{next_target:08X}u);",
            "}",
            "",
            *first_body,
            "",
            *next_body,
            "",
            "uint32_t tekken3_initializer_entry_boundary() {",
            f"  return 0x{initializer_start:08X}u;",
            "}",
            "uint32_t tekken3_initializer_return_boundary() {",
            f"  return 0x{return_boundary:08X}u;",
            "}",
            "uint32_t tekken3_next_initializer_boundary() {",
            f"  return 0x{next_target:08X}u;",
            "}",
            "",
        )
    )
    return GeneratedSlices(
        start,
        first_call_address,
        initializer_start,
        initializer_end,
        return_boundary,
        next_call_address,
        next_target,
        next_end,
        first_instructions,
        initializer_instructions,
        next_instructions,
        emitter.RECOMP_VERSION,
        source,
    )


def metadata(prefix: GeneratedSlices, executable: pathlib.Path) -> dict[str, object]:
    return {
        "emitter_version": prefix.emitter_version,
        "executable_sha256": sha256(executable),
        "first_initializer": {
            "end": f"0x{prefix.initializer_end:08X}",
            "instructions": prefix.initializer_instructions,
            "start": f"0x{prefix.initializer_start:08X}",
        },
        "game_main_first_slice": {
            "end": f"0x{prefix.return_boundary:08X}",
            "instructions": prefix.first_instructions,
            "start": f"0x{prefix.start:08X}",
        },
        "game_main_next_call": {
            "end": f"0x{prefix.next_end:08X}",
            "instructions": prefix.next_instructions,
            "start": f"0x{prefix.next_call_address:08X}",
            "target": f"0x{prefix.next_target:08X}",
        },
    }


def write_if_changed(path: pathlib.Path, text: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    path.write_text(text, encoding="utf-8")


def emit(executable: pathlib.Path, output: pathlib.Path) -> GeneratedSlices:
    prefix = render_slices(executable)
    output.mkdir(parents=True, exist_ok=True)
    write_if_changed(output / SOURCE, prefix.source)
    write_if_changed(
        output / METADATA,
        json.dumps(metadata(prefix, executable), indent=2, sort_keys=True) + "\n",
    )
    print(
        "PASS emission: executable-derived slices contain "
        f"{prefix.first_instructions} game_main + {prefix.initializer_instructions} initializer "
        f"+ {prefix.next_instructions} next-call instructions through 0x{prefix.next_target:08X}; "
        f"recompiler {prefix.emitter_version}"
    )
    return prefix


def inspect_generated(executable: pathlib.Path, output: pathlib.Path) -> GeneratedSlices:
    expected = render_slices(executable)
    try:
        actual_source = (output / SOURCE).read_text(encoding="utf-8")
        actual_metadata = json.loads((output / METADATA).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"generated boundary slices are incomplete: {exc}") from exc
    if actual_source != expected.source:
        raise Refused("generated slice source differs from current executable/recompiler output")
    if actual_metadata != metadata(expected, executable):
        raise Refused("generated slice metadata is stale or malformed")
    return expected


def parse_oracle_trace(text: str, *, target: int, delay_address: int) -> BoundaryState:
    initial = INITIAL_RE.search(text)
    if initial is None:
        raise Refused("oracle trace has no initial register state")
    fields = {name: 0 for name in REGISTER_NAMES}
    fields["gp"] = int(initial.group("gp"), 16)
    fields["sp"] = int(initial.group("sp"), 16)
    fields["pc"] = int(initial.group("pc"), 16)
    prior_pc = fields["pc"]
    captures: list[BoundaryState] = []

    for line in text.splitlines():
        match = TRACE_RE.match(line)
        if match is None:
            continue
        step = int(match.group("step"))
        pc = int(match.group("pc"), 16)
        for change in CHANGE_RE.finditer(match.group("changes")):
            name = change.group("name")
            if name not in fields:
                raise Refused(f"oracle trace changed unknown register {name!r}")
            fields[name] = int(change.group("value"), 16)
        fields["zero"] = 0
        fields["pc"] = pc
        if prior_pc == delay_address and pc == target:
            captures.append(BoundaryState("oracle", dict(fields), step))
        prior_pc = pc

    if not captures:
        raise Refused(
            f"oracle did not execute edge 0x{delay_address:08X} -> 0x{target:08X}"
        )
    if len(captures) != 1:
        raise Refused(
            f"oracle reached the requested edge {len(captures)} times; expected exactly once"
        )
    return captures[0]


def parse_recomp(text: str, expected_boundary: int) -> BoundaryState:
    translated = text.replace("# RECOMP-BOUNDARY", "# PSXPORT-BOUNDARY").replace(
        "# RECOMP-REG", "# PSXPORT-REG"
    )
    state = parse_psxport(translated, expected_boundary)
    return BoundaryState("generated port", state.fields)


def capture_oracle_trace(
    oracle: pathlib.Path,
    executable: pathlib.Path,
    steps: int,
    trace: pathlib.Path,
    timeout: float,
) -> str:
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.unlink(missing_ok=True)
    result = run_process(
        [str(oracle), str(executable), "--steps", str(steps), "--out", str(trace)],
        timeout,
    )
    if result.returncode != 0:
        raise Refused(
            f"oracle trace exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    if not trace.is_file():
        raise Refused(f"oracle reported success without writing {trace}")
    return trace.read_text(encoding="utf-8", errors="replace")


def capture_recomp(
    runner: pathlib.Path,
    executable: pathlib.Path,
    entry: int,
    direct_main: int,
    target: int,
    timeout: float,
) -> BoundaryState:
    result = run_process(
        [
            str(runner),
            str(executable),
            f"0x{entry:08X}",
            f"0x{direct_main:08X}",
            f"0x{target:08X}",
        ],
        timeout,
    )
    if result.returncode != 0:
        raise Refused(
            f"generated runner exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return parse_recomp(result.stdout, target)


def compare_boundary(
    executable: pathlib.Path,
    build: pathlib.Path,
    runner: pathlib.Path,
    output: pathlib.Path,
    *,
    steps: int,
    timeout: float,
    raw: pathlib.Path,
    force_mismatch: str | None = None,
) -> dict[str, tuple[BoundaryState, BoundaryState]]:
    manifest = load_manifest(MANIFEST)
    verify_startup(manifest, executable)
    prefix = inspect_generated(executable, output)
    check_tool(runner, "generated boundary runner")
    oracle = build / "psxport_build" / "tools" / "oracle" / "oracle_trace"
    check_tool(oracle, "oracle_trace")
    header = manifest.get("header")
    if not isinstance(header, dict):
        raise Refused("manifest field header must be an object")
    entry = parse_hex(header.get("entry"), "header.entry")
    trace_path = raw / "oracle.trace"
    trace_text = capture_oracle_trace(
        oracle,
        executable,
        steps,
        trace_path,
        timeout,
    )
    edges = (
        (
            "first initializer entry",
            prefix.initializer_start,
            prefix.first_call_address + 4,
        ),
        (
            "first initializer return",
            prefix.return_boundary,
            prefix.initializer_end - 4,
        ),
        (
            "next initializer entry",
            prefix.next_target,
            prefix.next_end - 4,
        ),
    )
    results: dict[str, tuple[BoundaryState, BoundaryState]] = {}
    for label, target, delay_address in edges:
        reference = parse_oracle_trace(
            trace_text,
            target=target,
            delay_address=delay_address,
        )
        port = capture_recomp(
            runner,
            executable,
            entry,
            prefix.start,
            target,
            timeout,
        )
        compared = port
        if force_mismatch and label == "first initializer return":
            if force_mismatch not in port.fields:
                raise Refused(f"unknown forced mismatch field {force_mismatch!r}")
            changed = dict(port.fields)
            changed[force_mismatch] ^= 1
            compared = BoundaryState("forced generated port", changed)
        total = compare_states(compared, reference)
        print(
            f"PASS {label}: true oracle and hybrid generated execution agree on "
            f"{total}/{total} CPU fields at 0x{target:08X} (oracle step {reference.step})"
        )
        results[label] = (reference, port)
    print(f"trace: {trace_path}")
    print("NOT covered: execution inside the second initializer, BIOS/devices, a frame, or gameplay")
    return results


def selftest(
    executable: pathlib.Path,
    build: pathlib.Path,
    runner: pathlib.Path,
    output: pathlib.Path,
    steps: int,
    timeout: float,
) -> None:
    prefix = inspect_generated(executable, output)
    print(
        "PASS generated integrity: exact executable slices contain "
        f"{prefix.first_instructions} + {prefix.initializer_instructions} + "
        f"{prefix.next_instructions} instructions"
    )
    results = compare_boundary(
        executable,
        build,
        runner,
        output,
        steps=steps,
        timeout=timeout,
        raw=DEFAULT_RAW,
    )
    reference, port = results["first initializer return"]
    changed = dict(port.fields)
    changed["a0"] ^= 1
    try:
        compare_states(BoundaryState("forced generated port", changed), reference)
    except Mismatch as exc:
        if "a0:" not in str(exc):
            raise Refused("opposite-answer comparison did not name a0") from exc
    else:
        raise Refused("opposite-answer comparison accepted an altered a0")
    print("PASS negative comparison: altered generated a0 is rejected by the production comparator")

    DEFAULT_RAW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stale-prefix-", dir=DEFAULT_RAW) as temporary:
        temporary_output = pathlib.Path(temporary)
        emit(executable, temporary_output)
        (temporary_output / SOURCE).write_text("stale\n", encoding="utf-8")
        try:
            inspect_generated(executable, temporary_output)
        except Refused:
            pass
        else:
            raise Refused("generated integrity check accepted altered slice source")
    print("PASS refusal: altered generated slice source is rejected")

    short_trace = (
        "# initial: pc=0x80010000 gp=0x00000000 sp=0x801FFFF0\n"
        "0 0x80010004 5"
    )
    try:
        parse_oracle_trace(short_trace, target=0x80010020, delay_address=0x8001001C)
    except Refused:
        pass
    else:
        raise Refused("oracle parser accepted a trace that never reached the call")
    print("PASS refusal: trace without the requested edge is rejected")

    manifest = load_manifest(MANIFEST)
    header = manifest.get("header")
    if not isinstance(header, dict):
        raise Refused("manifest field header must be an object")
    entry = parse_hex(header.get("entry"), "header.entry")
    try:
        capture_recomp(
            runner,
            executable,
            entry,
            prefix.start,
            prefix.next_target + 4,
            timeout,
        )
    except Refused:
        pass
    else:
        raise Refused("generated runner accepted an unmeasured boundary")
    print("PASS refusal: unmeasured generated boundary is rejected")
    print("SELFTEST 6/6")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=pathlib.Path, default=DEFAULT_EXE)
    parser.add_argument("--build", type=pathlib.Path, default=DEFAULT_BUILD)
    parser.add_argument("--runner", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_GENERATED)
    parser.add_argument("--steps", type=int, default=120_000)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--force-mismatch")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--emit", action="store_true")
    action.add_argument("--compare", action="store_true")
    action.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    runner = args.runner or args.build / "tekken3_recomp_boundary"
    try:
        if args.emit:
            emit(args.exe, args.output)
        elif args.selftest:
            selftest(args.exe, args.build, runner, args.output, args.steps, args.timeout)
        else:
            compare_boundary(
                args.exe,
                args.build,
                runner,
                args.output,
                steps=args.steps,
                timeout=args.timeout,
                raw=DEFAULT_RAW,
                force_mismatch=args.force_mismatch,
            )
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
