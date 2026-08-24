#!/usr/bin/env python3
"""Hermetic positive and refusal tests for the shipping launcher."""

from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

import run

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = REPO_ROOT / "scratch/raw"
LOCKED_PYTHON = "/locked/venv/bin/python"


class FakeHost(run.Host):
    def __init__(
        self,
        *,
        missing: set[str] | None = None,
        fail_token: str | None = None,
        system: str = "Linux",
        distribution: str = "fedora",
    ) -> None:
        self.missing = missing or set()
        self.fail_token = fail_token
        self.system_name = system
        self.distribution = distribution
        self.commands: list[tuple[list[str], dict[str, object]]] = []
        self.which_queries: list[str] = []

    def which(self, name: str) -> str | None:
        self.which_queries.append(name)
        return None if name in self.missing else f"/fake/{Path(name).name}"

    def system(self) -> str:
        return self.system_name

    def linux_distribution(self) -> str:
        return self.distribution

    def run(
        self, args: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        command = [str(arg) for arg in args]
        self.commands.append((command, kwargs))
        returncode = int(self.fail_token is not None and self.fail_token in command)
        stdout = ""
        if Path(command[0]).name == "getconf":
            stdout = "16"
        elif "rev-parse" in command:
            stdout = "abcdef12"
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


class LauncherTest(unittest.TestCase):
    def setUp(self) -> None:
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="run-selftest-", dir=SCRATCH)
        self.root = Path(self.temp.name)
        framework_cmake = self.root / "external/psxport/cmake/psxport.cmake"
        framework_cmake.parent.mkdir(parents=True)
        framework_cmake.write_text("# fixture\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def invoke(
        self,
        host: FakeHost,
        *argv: str,
        environment: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = run.run_launcher(
            argv,
            environ=environment or {"PATH": os.environ.get("PATH", "")},
            host=host,
            root=self.root,
            python_executable=LOCKED_PYTHON,
            stdout=stdout,
            stderr=stderr,
        )
        return code, stdout.getvalue(), stderr.getvalue()

    @staticmethod
    def commands(host: FakeHost) -> list[list[str]]:
        return [command for command, _ in host.commands]

    def test_default_provisions_builds_and_launches_product(self) -> None:
        host = FakeHost()
        code, stdout, stderr = self.invoke(host, "Tekken 3.chd")
        commands = self.commands(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("launching Tekken 3", stdout)
        self.assertIn([LOCKED_PYTHON, "tools/psxport_sync.py", "--auto"], commands)
        self.assertIn(
            [LOCKED_PYTHON, "-B", "tools/provision_executable.py", "Tekken 3.chd"],
            commands,
        )
        self.assertIn([LOCKED_PYTHON, "-B", "tools/ensure_recomp.py"], commands)
        self.assertTrue(commands[-1][0].endswith("scratch/bin/tekken3_port"))
        self.assertEqual(
            commands[-1][1],
            str(self.root / "scratch/bin/tekken3/SLUS_004.02"),
        )
        launch_environment = host.commands[-1][1]["env"]
        self.assertEqual(
            launch_environment["PSXPORT_TEKKEN3_DISC"],
            str(Path("Tekken 3.chd").resolve()),
        )
        self.assertFalse(any(Path(command[0]).name == "ctest" for command in commands))
        self.assertFalse(any("test" in command for command in commands))

        configure = next(command for command in commands if command[:2] == ["cmake", "-S"])
        self.assertIn(f"-DPython3_EXECUTABLE={LOCKED_PYTHON}", configure)
        self.assertFalse(any(option.startswith("-DCMAKE_C_COMPILER=") for option in configure))
        self.assertFalse(any(option.startswith("-DCMAKE_CXX_COMPILER=") for option in configure))
        self.assertEqual(host.which_queries, ["cmake", "git", "pkg-config"])

    def test_prepare_only_builds_product_without_launching(self) -> None:
        host = FakeHost()
        code, stdout, stderr = self.invoke(host, "--prepare-only")
        commands = self.commands(host)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("built and ready", stdout)
        self.assertIn(
            ["cmake", "--build", "build", "--target", "tekken3_port", "-j", "16"],
            commands,
        )
        self.assertFalse(any(command[0].endswith("tekken3_port") for command in commands))

    def test_nowindow_changes_only_final_launch_environment(self) -> None:
        host = FakeHost()
        code, _, stderr = self.invoke(
            host,
            environment={"PATH": os.environ.get("PATH", ""), "PSXPORT_NOWINDOW": "1"},
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        launch_environment = host.commands[-1][1]["env"]
        self.assertEqual(launch_environment["PSXPORT_VK_HEADLESS"], "1")
        self.assertNotIn("PSXPORT_VK_WINDOW", launch_environment)

    def test_missing_cmake_names_exact_fedora_install_before_mutation(self) -> None:
        host = FakeHost(missing={"cmake"})
        code, stdout, stderr = self.invoke(host)

        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("sudo dnf install cmake", stderr)
        self.assertEqual(host.commands, [])

    def test_missing_sdl3_names_exact_debian_install(self) -> None:
        host = FakeHost(fail_token="sdl3", distribution="ubuntu")
        code, _, stderr = self.invoke(host)

        self.assertEqual(code, 1)
        self.assertIn("sudo apt install libsdl3-dev", stderr)

    def test_explicit_framework_skips_auto_sync(self) -> None:
        host = FakeHost()
        framework = self.root / "framework-dev"
        cmake = framework / "cmake/psxport.cmake"
        cmake.parent.mkdir(parents=True)
        cmake.write_text("# fixture\n")
        code, _, stderr = self.invoke(
            host, "--prepare-only", environment={"PSXPORT_DIR": str(framework)}
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn(
            [LOCKED_PYTHON, "tools/psxport_sync.py", "--auto"], self.commands(host)
        )

    def test_provision_failure_stops_before_generation_or_player_build(self) -> None:
        host = FakeHost(fail_token="tools/provision_executable.py")
        code, _, stderr = self.invoke(host)
        commands = self.commands(host)

        self.assertEqual(code, 1)
        self.assertIn("executable provisioning failed", stderr)
        self.assertNotIn([LOCKED_PYTHON, "-B", "tools/ensure_recomp.py"], commands)
        self.assertFalse(any("tekken3_port" in command for command in commands))

    def test_shell_and_lock_are_stable_entry_contract(self) -> None:
        self.assertEqual(
            (REPO_ROOT / "run.sh").read_text(),
            '#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec uv run --frozen python bootstrap.py "$@"\n',
        )
        self.assertIn("from tools.run import main", (REPO_ROOT / "bootstrap.py").read_text())
        self.assertIn("package = false", (REPO_ROOT / "pyproject.toml").read_text())
        self.assertIn("version = 1", (REPO_ROOT / "uv.lock").read_text())
        self.assertTrue(os.access(REPO_ROOT / "run.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
