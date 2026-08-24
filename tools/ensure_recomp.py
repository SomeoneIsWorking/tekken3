#!/usr/bin/env python3
"""Keep Tekken 3's generated whole-program substrate aligned with measured inputs."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = ROOT / "scratch/bin/tekken3/SLUS_004.02"
MANIFEST = ROOT / "titles/tekken3/executable.json"
SEEDS = ROOT / "game/recomp_seeds.json"
GENERATED = ROOT / "generated/port"

sys.path.insert(0, str(ROOT / "tools"))
from provision_executable import (  # noqa: E402
    Mismatch,
    Refused,
    load_manifest,
    parse_hex,
    verify_executable,
)


class RecompError(RuntimeError):
    """The generated program cannot be proven current."""


def file_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            raise RecompError(f"required recomp input is absent: {path}")
        digest.update(path.name.encode())
        digest.update(b"\0")
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def recompiler_sources(psxport: Path) -> tuple[Path, ...]:
    directory = psxport / "tools/recomp"
    return tuple(directory / name for name in ("emit.py", "decode.py", "psexe.py"))


def recompiler_version(emitter: Path) -> str:
    match = re.search(
        r'^RECOMP_VERSION\s*=\s*"([^"]+)"', emitter.read_text(), re.MULTILINE
    )
    if match is None:
        raise RecompError(f"could not read RECOMP_VERSION from {emitter}")
    return match.group(1)


def manifest_program() -> tuple[int, int, int]:
    data = load_manifest(MANIFEST)
    header = data.get("header")
    if not isinstance(header, dict):
        raise RecompError("executable manifest has no header object")
    try:
        entry = parse_hex(header["entry"], "header.entry")
        text_address = parse_hex(header["text_address"], "header.text_address")
        text_size = parse_hex(header["text_size"], "header.text_size")
    except (KeyError, TypeError, ValueError, Refused) as error:
        raise RecompError(f"executable manifest has malformed program fields: {error}") from error
    return entry, text_address & 0x1FFF_FFFF, (text_address + text_size) & 0x1FFF_FFFF


def generated_sources() -> tuple[str, ...]:
    source_manifest = GENERATED / "rec_sources.cmake"
    if not source_manifest.is_file():
        return ()
    names = tuple(
        re.findall(r"^\s+(\S+\.c)\s*$", source_manifest.read_text(), re.MULTILINE)
    )
    return names if all((GENERATED / name).is_file() for name in names) else ()


def expected_program_header() -> str:
    entry, resident_lo, resident_hi = manifest_program()
    return (
        "// GENERATED from titles/tekken3/executable.json — DO NOT EDIT.\n"
        "#pragma once\n"
        f"#define TEKKEN3_PROGRAM_ENTRY 0x{entry:08X}u\n"
        f"#define TEKKEN3_RESIDENT_TEXT_LO 0x{resident_lo:08X}u\n"
        f"#define TEKKEN3_RESIDENT_TEXT_HI 0x{resident_hi:08X}u\n"
    )


def output_complete(version: str) -> bool:
    sources = generated_sources()
    version_file = GENERATED / ".recomp_version"
    program_header = GENERATED / "tekken3_program.h"
    return (
        bool(sources)
        and (GENERATED / "rec_decls.h").is_file()
        and (GENERATED / "overlay_table.h").is_file()
        and version_file.is_file()
        and version_file.read_text().strip() == version
        and program_header.is_file()
        and program_header.read_text() == expected_program_header()
    )


def ensure(psxport: Path) -> None:
    verify_executable(load_manifest(MANIFEST), EXECUTABLE)
    sources = recompiler_sources(psxport)
    version = recompiler_version(sources[0])
    wanted = f"{version}:{file_hash([EXECUTABLE, MANIFEST, SEEDS, *sources])}"
    hash_file = GENERATED / ".recomp.hash"
    have = hash_file.read_text().strip() if hash_file.is_file() else ""
    force = os.environ.get("PSXPORT_FORCE_RECOMP", "") not in ("", "0")
    if not force and have == wanted and output_complete(version):
        print(f"[ensure-recomp] whole-program substrate is current ({version})")
        return

    GENERATED.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    # Keep generated bodies small enough that a fresh-clone build can compile them in bounded
    # memory. The source manifest is consumed as a list, so this layout choice has no guest
    # semantic effect.
    environment.setdefault("PSXPORT_SHARDS", "128")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(sources[0]),
            str(EXECUTABLE),
            str(GENERATED / "main.c"),
            "--seeds",
            str(SEEDS),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise RecompError("whole-program substrate emission failed")
    (GENERATED / "tekken3_program.h").write_text(expected_program_header())
    if not output_complete(version):
        raise RecompError("emitter returned success but generated output is incomplete")
    hash_file.write_text(wanted + "\n")
    print(
        f"[ensure-recomp] whole-program substrate is current ({version}); "
        f"{len(generated_sources())} translation units"
    )


def main() -> int:
    psxport = Path(
        os.environ.get("PSXPORT_DIR", ROOT / "external/psxport")
    ).resolve()
    try:
        ensure(psxport)
    except (OSError, RecompError, Refused, Mismatch) as error:
        print(f"[ensure-recomp] REFUSED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
