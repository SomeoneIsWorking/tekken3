#!/usr/bin/env python3
"""Provision and verify Tekken 3's selected USA executable from the user's disc.

Resolution is deliberately deterministic: CLI argument, ``PSXPORT_TEKKEN3_DISC``,
``.env``, then one ``*.chd`` drop-in at the repository root. A configured path that
does not exist is an error; the tool never falls through to a different disc.

Exit 0 means the extracted executable matches every tracked identity/header field,
exit 1 means real bytes contradicted the manifest, and exit 2 means the comparison
could not be made. Disc-derived output remains below gitignored ``scratch/``.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "titles" / "tekken3" / "executable.json"
DISC_ENV = "PSXPORT_TEKKEN3_DISC"

PSXPORT = pathlib.Path(os.environ.get("PSXPORT_DIR", ROOT / "external" / "psxport"))
RECOMP_TOOLS = PSXPORT / "tools" / "recomp"
sys.path.insert(0, str(RECOMP_TOOLS))
try:
    import psexe
except ImportError as exc:
    raise SystemExit(
        f"REFUSED: cannot import psxport's PS-X EXE loader from {RECOMP_TOOLS}; "
        "run tools/psxport_sync.py --auto or set PSXPORT_DIR"
    ) from exc


class Refused(Exception):
    """The requested verification could not make a valid comparison."""


class Mismatch(Exception):
    """Measured bytes contradict the tracked executable manifest."""


def parse_hex(value: object, field: str) -> int:
    if not isinstance(value, str):
        raise Refused(f"manifest field {field} must be a hexadecimal string")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise Refused(f"manifest field {field} is not hexadecimal: {value!r}") from exc


def load_manifest(path: pathlib.Path = MANIFEST) -> dict[str, Any]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Refused(f"cannot read manifest {path}: {exc}") from exc
    required = {
        "title",
        "region",
        "serial",
        "disc_executable",
        "output_name",
        "file_size",
        "sha256",
        "header",
        "startup",
    }
    missing = sorted(required - manifest.keys())
    if missing:
        raise Refused(f"manifest {path} is missing {', '.join(missing)}")
    if not isinstance(manifest["header"], dict):
        raise Refused("manifest field header must be an object")
    return manifest


def dotenv_value(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise Refused(f"cannot read {path}: {exc}") from exc
    match = re.search(
        rf"^[ \t]*{re.escape(DISC_ENV)}[ \t]*=[ \t]*(.*?)[ \t]*$",
        text,
        re.MULTILINE,
    )
    if match is None:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value or None


def source_path(value: str, *, base: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    return path if path.is_absolute() else base / path


def resolve_disc(
    root: pathlib.Path,
    explicit: str | None,
    environ: Mapping[str, str],
) -> tuple[str, pathlib.Path]:
    selected: tuple[str, pathlib.Path] | None = None
    if explicit:
        selected = ("CLI argument", source_path(explicit, base=pathlib.Path.cwd()))
    elif environ.get(DISC_ENV):
        selected = (
            f"${DISC_ENV}",
            source_path(environ[DISC_ENV], base=root),
        )
    else:
        configured = dotenv_value(root / ".env")
        if configured:
            selected = (".env", source_path(configured, base=root))
        else:
            dropins = sorted(root.glob("*.chd"), key=lambda item: item.name.casefold())
            if len(dropins) > 1:
                names = ", ".join(item.name for item in dropins)
                raise Refused(
                    f"multiple root CHD drop-ins are ambiguous: {names}; pass the intended disc"
                )
            if dropins:
                selected = ("root *.chd drop-in", dropins[0])

    if selected is None:
        raise Refused(
            "no disc image; tried a CLI argument, "
            f"${DISC_ENV}, .env, and one *.chd in {root}"
        )
    source, path = selected
    if not path.is_file():
        raise Refused(f"{source} names {path}, which is not a file")
    return source, path.resolve()


def expected_header(manifest: Mapping[str, Any]) -> dict[str, int]:
    header = manifest["header"]
    if not isinstance(header, dict):
        raise Refused("manifest field header must be an object")
    return {
        key: parse_hex(header.get(key), f"header.{key}")
        for key in (
            "entry",
            "gp",
            "text_address",
            "text_size",
            "stack_address",
            "stack_offset",
        )
    }


def verify_executable(manifest: Mapping[str, Any], path: pathlib.Path) -> None:
    try:
        data = path.read_bytes()
        image = psexe.load(str(path))
    except OSError as exc:
        raise Refused(f"cannot read {path}: {exc}") from exc
    except ValueError as exc:
        raise Mismatch(f"{path.name} is not a valid PS-X EXE: {exc}") from exc

    header = expected_header(manifest)
    measured = {
        "file_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "entry": image.entry,
        "gp": image.gp,
        "text_address": image.load,
        "text_size": image.text_size,
        "stack_address": image.sp_base,
        "stack_offset": image.sp_off,
    }
    expected = {
        "file_size": manifest["file_size"],
        "sha256": manifest["sha256"],
        **header,
    }
    failures = [
        f"{field}: expected {want!r}, measured {measured[field]!r}"
        for field, want in expected.items()
        if measured[field] != want
    ]
    if failures:
        raise Mismatch("; ".join(failures))

    print(
        f"[provision] MATCH 8/8 identity/header facts: {path.name}, {len(data)} bytes, "
        f"sha256={measured['sha256']}"
    )
    print(
        f"[provision] entry=0x{image.entry:08X}, text=[0x{image.load:08X},"
        f"0x{image.text_end:08X}), stack=0x{image.sp_base + image.sp_off:08X}"
    )


def discdump_path(root: pathlib.Path, environ: Mapping[str, str]) -> pathlib.Path:
    configured = environ.get("PSXPORT_DISCDUMP")
    path = (
        source_path(configured, base=pathlib.Path.cwd())
        if configured
        else root / "build" / "psxport_build" / "tools" / "discdump"
    )
    if not path.is_file() or not os.access(path, os.X_OK):
        raise Refused(
            f"discdump is not executable at {path}; build the Clang target with "
            "`cmake --build build --target discdump` or set PSXPORT_DISCDUMP"
        )
    return path


def provision(
    manifest: Mapping[str, Any],
    root: pathlib.Path,
    disc: pathlib.Path,
    environ: Mapping[str, str],
) -> pathlib.Path:
    tool = discdump_path(root, environ)
    output_dir = root / "scratch" / "bin" / "tekken3"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / str(manifest["output_name"])
    with tempfile.TemporaryDirectory(prefix="extract-", dir=output_dir) as temp:
        staging_dir = pathlib.Path(temp)
        staged = staging_dir / str(manifest["output_name"])
        command = [
            str(tool),
            "get",
            str(manifest["disc_executable"]),
            str(disc),
            str(staging_dir),
        ]
        result = subprocess.run(command, check=False, env=dict(environ))
        if result.returncode != 0:
            raise Refused(f"discdump failed with exit {result.returncode}")
        if not staged.is_file():
            raise Refused(
                f"discdump reported success but did not create {staged}; "
                f"the disc may not contain {manifest['disc_executable']}"
            )
        verify_executable(manifest, staged)
        os.replace(staged, destination)
    return destination


def run(
    explicit: str | None,
    *,
    root: pathlib.Path = ROOT,
    environ: Mapping[str, str] = os.environ,
    manifest_path: pathlib.Path = MANIFEST,
) -> pathlib.Path:
    manifest = load_manifest(manifest_path)
    source, disc = resolve_disc(root, explicit, environ)
    print(f"[provision] disc from {source}: {disc}")
    destination = provision(manifest, root, disc, environ)
    print(f"[provision] ready: {destination}")
    return destination


def synthetic_executable() -> bytes:
    data = bytearray(0x900)
    data[:8] = b"PS-X EXE"
    struct.pack_into("<II", data, 0x10, 0x80010040, 0)
    struct.pack_into("<II", data, 0x18, 0x80010000, 0x100)
    struct.pack_into("<II", data, 0x30, 0x801FFF00, 0x40)
    return bytes(data)


def selftest() -> bool:
    results: list[tuple[str, bool]] = []
    scratch = ROOT / "scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="provision-selftest-", dir=scratch) as temp:
        test_root = pathlib.Path(temp)
        data = synthetic_executable()
        sources = {
            "cli": test_root / "cli.chd",
            "env": test_root / "env.chd",
            "dotenv": test_root / "dotenv.chd",
            "drop": test_root / "drop.chd",
        }
        for path in sources.values():
            path.write_bytes(data)

        manifest = {
            "title": "fixture",
            "region": "test",
            "serial": "TEST",
            "disc_executable": "GAME/TEST.EXE",
            "output_name": "TEST.EXE",
            "file_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "header": {
                "entry": "0x80010040",
                "gp": "0x00000000",
                "text_address": "0x80010000",
                "text_size": "0x00000100",
                "stack_address": "0x801FFF00",
                "stack_offset": "0x00000040",
            },
            "startup": {},
        }
        manifest_path = test_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        (test_root / ".env").write_text(
            f'{DISC_ENV}="{sources["dotenv"]}"\n', encoding="utf-8"
        )

        source, path = resolve_disc(
            test_root, str(sources["cli"]), {DISC_ENV: str(sources["env"])}
        )
        results.append(
            (
                "CLI outranks environment and .env",
                source == "CLI argument" and path == sources["cli"],
            )
        )
        source, path = resolve_disc(test_root, None, {DISC_ENV: str(sources["env"])})
        results.append(
            (
                "environment outranks .env",
                source == f"${DISC_ENV}" and path == sources["env"],
            )
        )
        source, path = resolve_disc(test_root, None, {})
        results.append(
            (
                ".env outranks root drop-in",
                source == ".env" and path == sources["dotenv"],
            )
        )
        (test_root / ".env").unlink()
        for key in ("cli", "env", "dotenv"):
            sources[key].unlink()
        source, path = resolve_disc(test_root, None, {})
        results.append(
            (
                "single root drop-in resolves",
                source == "root *.chd drop-in" and path == sources["drop"],
            )
        )

        missing_refused = False
        try:
            resolve_disc(test_root, "missing.chd", {})
        except Refused:
            missing_refused = True
        results.append(
            ("missing configured path refuses without fallback", missing_refused)
        )

        second_drop = test_root / "second.chd"
        second_drop.write_bytes(data)
        ambiguous_refused = False
        try:
            resolve_disc(test_root, None, {})
        except Refused:
            ambiguous_refused = True
        results.append(("multiple root drop-ins refuse ambiguity", ambiguous_refused))
        second_drop.unlink()

        fake = test_root / "fake_discdump.py"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, shutil, sys\n"
            "mode = os.environ.get('PROVISION_SELFTEST_MODE', 'copy')\n"
            "if mode == 'fail': raise SystemExit(7)\n"
            "if mode == 'missing': raise SystemExit(0)\n"
            "source = pathlib.Path(sys.argv[3])\n"
            "dest = pathlib.Path(sys.argv[4]) / 'TEST.EXE'\n"
            "shutil.copyfile(source, dest)\n"
            "if mode == 'mutate':\n"
            "    blob = bytearray(dest.read_bytes()); blob[-1] ^= 1; dest.write_bytes(blob)\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        base_env = {
            "PATH": os.environ.get("PATH", ""),
            "PSXPORT_DISCDUMP": str(fake),
        }

        def silent_run(env: Mapping[str, str]) -> type[Exception] | None:
            try:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    run(
                        str(sources["drop"]),
                        root=test_root,
                        environ=env,
                        manifest_path=manifest_path,
                    )
                return None
            except (Mismatch, Refused) as exc:
                return type(exc)

        results.append(
            (
                "shipping path provisions a matching executable",
                silent_run(base_env) is None,
            )
        )
        results.append(
            (
                "changed executable reports mismatch",
                silent_run({**base_env, "PROVISION_SELFTEST_MODE": "mutate"})
                is Mismatch,
            )
        )
        malformed = bytearray(data)
        malformed[0] ^= 1
        sources["drop"].write_bytes(malformed)
        results.append(
            (
                "malformed PS-X EXE reports mismatch",
                silent_run(base_env) is Mismatch,
            )
        )
        sources["drop"].write_bytes(data)
        installed = test_root / "scratch" / "bin" / "tekken3" / "TEST.EXE"
        results.append(
            (
                "failed replacement preserves the last verified executable",
                installed.is_file() and installed.read_bytes() == data,
            )
        )
        results.append(
            (
                "success without output is refused",
                silent_run({**base_env, "PROVISION_SELFTEST_MODE": "missing"})
                is Refused,
            )
        )
        results.append(
            (
                "discdump failure is refused",
                silent_run({**base_env, "PROVISION_SELFTEST_MODE": "fail"}) is Refused,
            )
        )

    for name, passed in results:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    passed_count = sum(passed for _, passed in results)
    print(f"provision selftest: {passed_count}/{len(results)} cases")
    return all(passed for _, passed in results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("disc", nargs="?", help="Tekken 3 USA CHD")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="exercise precedence, match, mismatch, and refusal through the shipping path",
    )
    args = parser.parse_args(argv)
    if args.selftest:
        return 0 if selftest() else 1
    try:
        run(args.disc)
        return 0
    except Mismatch as exc:
        print(f"MISMATCH: {exc}", file=sys.stderr)
        return 1
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
