#!/usr/bin/env python3
"""Provision, build, and launch the Tekken 3 port."""

from __future__ import annotations

import argparse
import os
import platform
import runpy
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
CYAN = "\033[1;36m"
RED = "\033[1;31m"
RESET = "\033[0m"


class LauncherFailure(RuntimeError):
    """A user-facing launcher refusal."""


class Host:
    """Injectable seam around host discovery and process execution."""

    @staticmethod
    def which(name: str) -> str | None:
        return shutil.which(name)

    @staticmethod
    def run(args: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess:
        check = bool(kwargs.pop("check", False))
        return subprocess.run(list(args), check=check, **kwargs)

    @staticmethod
    def system() -> str:
        return platform.system()

    @staticmethod
    def linux_distribution() -> str:
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                key, separator, value = line.partition("=")
                if separator and key == "ID":
                    return value.strip().strip('"').lower()
        except OSError:
            pass
        return "unknown"


def say(message: str, stdout: TextIO) -> None:
    print(f"{CYAN}[run]{RESET} {message}", file=stdout)


def package_command(host: Host, dependency: str) -> str | None:
    system = host.system()
    if system == "Darwin":
        return {
            "cmake": "brew install cmake",
            "git": "xcode-select --install",
            "pkg-config": "brew install pkg-config",
            "sdl3": "brew install sdl3",
            "sdl3-image": "brew install sdl3_image",
            "freetype2": "brew install freetype",
            "libzstd": "brew install zstd",
        }[dependency]
    if system == "Windows":
        return {
            "cmake": "winget install Kitware.CMake",
            "git": "winget install Git.Git",
            "pkg-config": "vcpkg install pkgconf",
            "sdl3": "vcpkg install sdl3",
            "sdl3-image": "vcpkg install sdl3-image",
            "freetype2": "vcpkg install freetype",
            "libzstd": "vcpkg install zstd",
        }[dependency]
    if system != "Linux":
        return None
    distribution = host.linux_distribution()
    if distribution in {"fedora", "rhel", "centos", "rocky", "almalinux"}:
        return {
            "cmake": "sudo dnf install cmake",
            "git": "sudo dnf install git",
            "pkg-config": "sudo dnf install pkgconf-pkg-config",
            "sdl3": "sudo dnf install SDL3-devel",
            "sdl3-image": "sudo dnf install SDL3_image-devel",
            "freetype2": "sudo dnf install freetype-devel",
            "libzstd": "sudo dnf install libzstd-devel",
        }[dependency]
    if distribution in {"debian", "ubuntu", "linuxmint", "pop"}:
        return {
            "cmake": "sudo apt install cmake",
            "git": "sudo apt install git",
            "pkg-config": "sudo apt install pkg-config",
            "sdl3": "sudo apt install libsdl3-dev",
            "sdl3-image": "sudo apt install libsdl3-image-dev",
            "freetype2": "sudo apt install libfreetype-dev",
            "libzstd": "sudo apt install libzstd-dev",
        }[dependency]
    return None


def missing_dependency(host: Host, name: str, package: str) -> LauncherFailure:
    command = package_command(host, package)
    if command:
        return LauncherFailure(f"{name} not found. Install it with: {command}")
    system = host.system()
    distribution = host.linux_distribution() if system == "Linux" else "unknown"
    return LauncherFailure(
        f"{name} not found, and no package command is recorded for {system}/{distribution}; "
        "install it with your platform package manager and rerun"
    )


def require_tool(host: Host, name: str) -> None:
    if host.which(name) is None:
        raise missing_dependency(host, name, name)


def run_stage(
    host: Host,
    args: Sequence[str],
    failure: str,
    *,
    root: Path,
    environment: Mapping[str, str],
) -> None:
    try:
        result = host.run(args, cwd=root, env=dict(environment), check=False)
    except OSError as error:
        raise LauncherFailure(f"{failure}: {error}") from error
    if result.returncode != 0:
        raise LauncherFailure(failure)


def command_output(host: Host, args: Sequence[str], *, root: Path) -> tuple[int, str]:
    try:
        result = host.run(
            args,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    except OSError:
        return 127, ""
    return result.returncode, result.stdout.strip()


def require_libraries(host: Host, *, root: Path, environment: Mapping[str, str]) -> None:
    for module, label, package in (
        ("sdl3", "SDL3 development files", "sdl3"),
        ("sdl3-image", "SDL3_image development files", "sdl3-image"),
        ("freetype2", "FreeType development files", "freetype2"),
        ("libzstd", "zstd development files", "libzstd"),
    ):
        run_stage(
            host,
            ["pkg-config", "--exists", module],
            str(missing_dependency(host, label, package)),
            root=root,
            environment=environment,
        )


def cpu_jobs(host: Host, *, root: Path) -> str:
    for command in (["getconf", "_NPROCESSORS_ONLN"], ["sysctl", "-n", "hw.ncpu"]):
        returncode, output = command_output(host, command, root=root)
        if returncode == 0 and output.isdigit() and int(output) > 0:
            return output
    return "4"


def framework_revision(host: Host, path: Path, *, root: Path) -> tuple[str, bool]:
    returncode, revision = command_output(
        host, ["git", "-C", str(path), "rev-parse", "--short", "HEAD"], root=root
    )
    if returncode != 0 or not revision:
        revision = "?"
    _, status = command_output(
        host, ["git", "-C", str(path), "status", "--porcelain"], root=root
    )
    return revision, bool(status)


def announce_framework(
    host: Host, setting: str, path: Path, *, root: Path, stdout: TextIO
) -> None:
    revision, dirty = framework_revision(host, path, root=root)
    suffix = " +dirty" if dirty else ""
    if setting == "external/psxport":
        say(f"framework: external/psxport -> {path.resolve()} @ {revision}{suffix}", stdout)
    else:
        say(
            f"framework: *** {setting} *** (DEV CLONE {revision}{suffix}) — NOT the recorded pin",
            stdout,
        )


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument(
        "-h",
        "--help",
        action="store_true",
        help="show this help message and exit",
    )
    parser.add_argument("disc", nargs="?", help="path to the user's Tekken 3 USA disc image")
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="provision and build the player product without launching it",
    )
    return parser


def run_launcher(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    host: Host | None = None,
    root: Path = ROOT,
    python_executable: str = sys.executable,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    environment = dict(os.environ if environ is None else environ)
    machine = host or Host()
    try:
        parser = argument_parser()
        options = parser.parse_args(list(argv))
        if options.help:
            parser.print_help(file=stdout)
            return 0
        for tool in ("cmake", "git", "pkg-config"):
            require_tool(machine, tool)
        require_libraries(machine, root=root, environment=environment)

        setting = environment.get("PSXPORT_DIR") or "external/psxport"
        if "PSXPORT_DIR" not in environment:
            run_stage(
                machine,
                [python_executable, "tools/psxport_sync.py", "--auto"],
                "could not resolve external/psxport",
                root=root,
                environment=environment,
            )
        framework = Path(setting)
        if not framework.is_absolute():
            framework = root / framework
        if not (framework / "cmake/psxport.cmake").is_file():
            raise LauncherFailure(f"PSXPORT_DIR={setting} is not a psxport checkout")
        announce_framework(machine, setting, framework, root=root, stdout=stdout)

        stage_environment = dict(environment)
        stage_environment["PSXPORT_DIR"] = str(framework)
        configure = [
            "cmake",
            "-S",
            ".",
            "-B",
            "build",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DPSXPORT_DIR={framework.absolute()}",
            f"-DPython3_EXECUTABLE={python_executable}",
        ]
        jobs = cpu_jobs(machine, root=root)
        run_stage(
            machine,
            configure,
            "cmake configure failed",
            root=root,
            environment=stage_environment,
        )
        run_stage(
            machine,
            ["cmake", "--build", "build", "--target", "discdump", "-j", jobs],
            "discdump build failed",
            root=root,
            environment=stage_environment,
        )
        provision = [python_executable, "-B", "tools/provision_executable.py"]
        if options.disc:
            provision.append(options.disc)
        run_stage(
            machine,
            provision,
            "Tekken 3 executable provisioning failed",
            root=root,
            environment=stage_environment,
        )
        say("building the Tekken 3 native/Lightrec product…", stdout)
        run_stage(
            machine,
            ["cmake", "--build", "build", "--target", "tekken3_port", "-j", jobs],
            "Tekken 3 player build failed",
            root=root,
            environment=stage_environment,
        )
    except LauncherFailure as error:
        print(f"{RED}[run] error:{RESET} {error}", file=stderr)
        return 1

    if options.prepare_only:
        say("Tekken 3 is built and ready.", stdout)
        return 0

    policy = runpy.run_path(str(framework / "tools/port/launch_environment.py"))
    launch_environment = policy["player_environment"](environment)
    if options.disc:
        launch_environment["PSXPORT_TEKKEN3_DISC"] = str(
            Path(options.disc).expanduser().resolve()
        )
    launch_environment.setdefault("PSXPORT_ASSET_DIR", str(framework))
    say("launching Tekken 3…", stdout)
    try:
        result = machine.run(
            [
                str(root / "build/bin/tekken3_port"),
                str(root / "scratch/bin/tekken3/SLUS_004.02"),
            ],
            cwd=root,
            env=launch_environment,
            check=False,
        )
    except OSError as error:
        print(f"{RED}[run] error:{RESET} launch failed: {error}", file=stderr)
        return 1
    return result.returncode


def main(argv: Sequence[str] | None = None) -> int:
    return run_launcher(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
