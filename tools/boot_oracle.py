#!/usr/bin/env python3
"""Compare Tekken's direct-main call boundary in psxport and an independent oracle.

The psxport leg executes the real entry window with the framework MIPS interpreter. The
reference leg executes the same bytes in vendored Mednafen through ``oracle_trace``. Both
stop semantically at the first call target recorded by the game manifest: after the JAL
delay slot and before ``game_main`` executes. No libc/InitHeap boundary is inferred.

Exit 0 means two deterministic runs per leg agree on all 35 CPU fields, exit 1 means a
real or explicitly forced disagreement, and exit 2 means the comparison could not be made.
This is an executable-boundary gate, not a substrate, device, frame, or gameplay gate.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from provision_executable import (
    MANIFEST,
    ROOT,
    Mismatch,
    Refused,
    load_manifest,
    parse_hex,
)
from verify_startup import startup_fields, verify_startup

REGISTER_NAMES = (
    "zero",
    "at",
    "v0",
    "v1",
    "a0",
    "a1",
    "a2",
    "a3",
    "t0",
    "t1",
    "t2",
    "t3",
    "t4",
    "t5",
    "t6",
    "t7",
    "s0",
    "s1",
    "s2",
    "s3",
    "s4",
    "s5",
    "s6",
    "s7",
    "t8",
    "t9",
    "k0",
    "k1",
    "gp",
    "sp",
    "fp",
    "ra",
    "lo",
    "hi",
    "pc",
)
REQUIRED_FIELDS = frozenset(REGISTER_NAMES)


@dataclass(frozen=True)
class BoundaryState:
    source: str
    fields: dict[str, int]
    step: int | None = None


def run_process(
    command: Sequence[str], timeout: float
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # This is the exact child PID returned by Popen; no name-based/shared-process kill is used.
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
        raise Refused(
            f"child pid {process.pid} exceeded {timeout:g}s and was stopped; command: "
            + " ".join(command)
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def require_fields(source: str, fields: dict[str, int]) -> None:
    missing = sorted(REQUIRED_FIELDS - fields.keys())
    if missing:
        raise Refused(
            f"{source} omitted {len(missing)} required field(s): {', '.join(missing)}"
        )


def parse_psxport(text: str, expected_boundary: int) -> BoundaryState:
    header = re.search(r"^# PSXPORT-BOUNDARY pc=0x([0-9A-Fa-f]+)", text, re.MULTILINE)
    if header is None:
        raise Refused("psxport probe emitted no boundary header")
    fields: dict[str, int] = {"pc": int(header.group(1), 16)}
    for name, value in re.findall(
        r"^# PSXPORT-REG (\w+)=0x([0-9A-Fa-f]+)$", text, re.MULTILINE
    ):
        fields[name] = int(value, 16)
    require_fields("psxport probe", fields)
    if fields["pc"] != expected_boundary:
        raise Refused(
            f"psxport stopped at 0x{fields['pc']:08X}, expected 0x{expected_boundary:08X}"
        )
    return BoundaryState("psxport", fields)


def parse_oracle(text: str, expected_boundary: int) -> BoundaryState:
    capture = re.search(
        r"^# CAPTURED-CALL target=0x([0-9A-Fa-f]+) ra=0x[0-9A-Fa-f]+ step=(\d+)$",
        text,
        re.MULTILINE,
    )
    header = re.search(
        r"^# CALL-BOUNDARY-REGS step=(\d+) pc=0x([0-9A-Fa-f]+)$",
        text,
        re.MULTILINE,
    )
    if capture is None or header is None:
        raise Refused("oracle trace emitted no captured first-call boundary")
    target = int(capture.group(1), 16)
    capture_step = int(capture.group(2))
    header_step = int(header.group(1))
    fields: dict[str, int] = {"zero": 0, "pc": int(header.group(2), 16)}
    for name, value in re.findall(
        r"^# CALL-BOUNDARY-REG (\w+)=0x([0-9A-Fa-f]+)$",
        text,
        re.MULTILINE,
    ):
        fields[name] = int(value, 16)
    require_fields("oracle trace", fields)
    if capture_step != header_step:
        raise Refused(
            f"oracle capture step {capture_step} differs from register step {header_step}"
        )
    if target != expected_boundary or fields["pc"] != expected_boundary:
        raise Refused(
            f"oracle captured target 0x{target:08X}/pc 0x{fields['pc']:08X}, "
            f"expected 0x{expected_boundary:08X}"
        )
    return BoundaryState("oracle", fields, capture_step)


def compare_states(psxport: BoundaryState, oracle: BoundaryState) -> int:
    require_fields(psxport.source, psxport.fields)
    require_fields(oracle.source, oracle.fields)
    disagreements = [
        name for name in REGISTER_NAMES if psxport.fields[name] != oracle.fields[name]
    ]
    if disagreements:
        detail = "; ".join(
            f"{name}: psxport=0x{psxport.fields[name]:08X}, "
            f"oracle=0x{oracle.fields[name]:08X}"
            for name in disagreements
        )
        raise Mismatch(
            f"{len(disagreements)} of {len(REGISTER_NAMES)} boundary fields disagree: {detail}"
        )
    return len(REGISTER_NAMES)


def run_psxport(
    probe: pathlib.Path,
    executable: pathlib.Path,
    entry: int,
    boundary: int,
    timeout: float,
) -> BoundaryState:
    result = run_process(
        [
            str(probe),
            str(executable),
            "--entry",
            f"0x{entry:08X}",
            "--boundary",
            f"0x{boundary:08X}",
        ],
        timeout,
    )
    if result.returncode != 0:
        raise Refused(
            f"psxport probe exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return parse_psxport(result.stdout, boundary)


def run_oracle(
    oracle: pathlib.Path,
    executable: pathlib.Path,
    boundary: int,
    steps: int,
    trace: pathlib.Path,
    timeout: float,
) -> BoundaryState:
    trace.parent.mkdir(parents=True, exist_ok=True)
    trace.unlink(missing_ok=True)
    result = run_process(
        [
            str(oracle),
            str(executable),
            "--steps",
            str(steps),
            "--capture-first-call",
            "--summary-only",
            "--out",
            str(trace),
        ],
        timeout,
    )
    if result.returncode != 0:
        raise Refused(
            f"oracle trace exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    if not trace.is_file():
        raise Refused(f"oracle reported success without writing {trace}")
    return parse_oracle(trace.read_text(encoding="utf-8", errors="replace"), boundary)


def check_tool(path: pathlib.Path, label: str) -> None:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise Refused(f"{label} is not executable at {path}")


def run_harness(
    manifest: Mapping[str, Any],
    executable: pathlib.Path,
    probe: pathlib.Path,
    oracle: pathlib.Path,
    *,
    steps: int,
    timeout: float,
    output_dir: pathlib.Path,
    force_mismatch: str | None = None,
) -> int:
    if steps <= 0:
        raise Refused("--steps must be positive")
    check_tool(probe, "psxport boot probe")
    check_tool(oracle, "oracle_trace")
    verify_startup(manifest, executable)
    startup = startup_fields(manifest)
    header = manifest.get("header")
    if not isinstance(header, dict):
        raise Refused("manifest field header must be an object")
    entry = parse_hex(header.get("entry"), "header.entry")
    boundary = int(startup["call_target"])

    port_runs = [
        run_psxport(probe, executable, entry, boundary, timeout) for _ in range(2)
    ]
    oracle_runs = [
        run_oracle(
            oracle,
            executable,
            boundary,
            steps,
            output_dir / f"reference-{index + 1}.txt",
            timeout,
        )
        for index in range(2)
    ]
    if port_runs[0].fields != port_runs[1].fields:
        raise Refused(
            "psxport produced different boundary states on two identical runs"
        )
    if (
        oracle_runs[0].fields != oracle_runs[1].fields
        or oracle_runs[0].step != oracle_runs[1].step
    ):
        raise Refused(
            "oracle produced different boundary states/steps on two identical runs"
        )

    compared_oracle = oracle_runs[0]
    if force_mismatch:
        if force_mismatch not in REQUIRED_FIELDS:
            raise Refused(f"unknown --force-mismatch field {force_mismatch!r}")
        changed = dict(compared_oracle.fields)
        changed[force_mismatch] ^= 1
        compared_oracle = BoundaryState("forced oracle", changed, compared_oracle.step)
        print(
            f"[boot-oracle] forced negative: flipped oracle field {force_mismatch} "
            "after deterministic capture"
        )

    compared = compare_states(port_runs[0], compared_oracle)
    print(
        f"[boot-oracle] deterministic: psxport 2/2 and oracle 2/2 identical; "
        f"oracle call step {oracle_runs[0].step}"
    )
    print(
        f"[boot-oracle] AGREEMENT {compared}/{len(REGISTER_NAMES)} CPU fields at "
        f"direct-main 0x{boundary:08X}"
    )
    print(f"[boot-oracle] traces: {output_dir}")
    print(
        "[boot-oracle] NOT covered: generated substrate, BIOS/device execution, frames, or gameplay"
    )
    return compared


def fixture_executable() -> bytearray:
    data = bytearray(0x840)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<II", data, 0x10, 0x80010000, 0)
    struct.pack_into("<II", data, 0x18, 0x80010000, 0x40)
    struct.pack_into("<II", data, 0x30, 0x801FFF00, 0)

    def store(address: int, word: int) -> None:
        struct.pack_into("<I", data, 0x800 + address - 0x80010000, word)

    store(0x80010000, 0x24041234)  # addiu a0, zero, 0x1234
    store(0x80010004, 0x24055678)  # addiu a1, zero, 0x5678
    store(0x80010008, (3 << 26) | ((0x80010020 >> 2) & 0x03FFFFFF))
    store(0x8001000C, 0)  # jal delay slot
    store(0x80010010, 0x0000000D)  # return guard: break
    store(0x80010030, (2 << 26) | ((0x80010020 >> 2) & 0x03FFFFFF))
    return data


def fixture_manifest(data: bytes) -> dict[str, Any]:
    return {
        "title": "boot oracle fixture",
        "region": "test",
        "serial": "TEST",
        "disc_executable": "TEST.EXE",
        "output_name": "TEST.EXE",
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "header": {
            "entry": "0x80010000",
            "gp": "0x00000000",
            "text_address": "0x80010000",
            "text_size": "0x00000040",
            "stack_address": "0x801FFF00",
            "stack_offset": "0x00000000",
        },
        "startup": {
            "shape": "direct_main",
            "entry_call": {
                "address": "0x80010008",
                "target": "0x80010020",
                "delay_slot": "nop",
                "return_guard_address": "0x80010010",
                "return_guard": "break",
            },
            "main_loop": {
                "back_edge_address": "0x80010030",
                "back_edge_target": "0x80010020",
            },
        },
    }


def selftest(probe: pathlib.Path, oracle: pathlib.Path, timeout: float) -> bool:
    results: list[tuple[str, bool]] = []
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="boot-oracle-selftest-", dir=scratch
    ) as temp:
        directory = pathlib.Path(temp)
        data = fixture_executable()
        executable = directory / "TEST.EXE"
        executable.write_bytes(data)
        manifest = fixture_manifest(data)

        def attempt(**kwargs: Any) -> Exception | None:
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    run_harness(
                        manifest,
                        executable,
                        probe,
                        oracle,
                        steps=kwargs.get("steps", 32),
                        timeout=timeout,
                        output_dir=directory / kwargs.get("name", "positive"),
                        force_mismatch=kwargs.get("force_mismatch"),
                    )
                return None
            except (Mismatch, Refused) as exc:
                return exc

        positive_error = attempt(name="positive")
        results.append(("two real engines agree", positive_error is None))
        negative_error = attempt(name="negative", force_mismatch="a0")
        results.append(
            (
                "forced register disagreement is detected",
                isinstance(negative_error, Mismatch),
            )
        )
        refusal_error = attempt(name="refusal", steps=1)
        results.append(
            (
                "too-short oracle window refuses zero-boundary compare",
                isinstance(refusal_error, Refused),
            )
        )

    errors = (positive_error, negative_error, refusal_error)
    for (name, passed), error in zip(results, errors, strict=True):
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        if not passed and error is not None:
            print(f"  observed {type(error).__name__}: {error}")
    passed_count = sum(passed for _, passed in results)
    print(f"boot oracle selftest: {passed_count}/{len(results)} cases")
    return all(passed for _, passed in results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exe",
        type=pathlib.Path,
        default=ROOT / "scratch" / "bin" / "tekken3" / "SLUS_004.02",
    )
    parser.add_argument(
        "--probe",
        type=pathlib.Path,
        default=ROOT / "scratch" / "bin" / "tekken3_boot_probe",
    )
    parser.add_argument(
        "--oracle",
        type=pathlib.Path,
        default=ROOT / "build" / "psxport_build" / "tools" / "oracle" / "oracle_trace",
    )
    parser.add_argument("--steps", type=int, default=400000)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--force-mismatch", metavar="FIELD")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.selftest:
            return 0 if selftest(args.probe, args.oracle, args.timeout) else 1
        run_harness(
            load_manifest(MANIFEST),
            args.exe,
            args.probe,
            args.oracle,
            steps=args.steps,
            timeout=args.timeout,
            output_dir=ROOT / "scratch" / "logs" / "boot-oracle",
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
