#!/usr/bin/env python3
"""Contract test for the shipping launcher's dependency-free help path."""

from __future__ import annotations

import io
import subprocess
import unittest
from collections.abc import Sequence

import run


class ForbiddenHost(run.Host):
    """Fail if help handling reaches any host or asset discovery operation."""

    @staticmethod
    def which(name: str) -> str | None:
        raise AssertionError(f"help queried host tool {name}")

    @staticmethod
    def run(
        args: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"help ran host command {list(args)}")

    @staticmethod
    def system() -> str:
        raise AssertionError("help queried the host operating system")

    @staticmethod
    def linux_distribution() -> str:
        raise AssertionError("help queried the host Linux distribution")


class LauncherHelpContractTest(unittest.TestCase):
    def test_short_and_long_help_exit_without_host_discovery(self) -> None:
        for flag in ("-h", "--help"):
            with self.subTest(flag=flag):
                stdout = io.StringIO()
                stderr = io.StringIO()

                code = run.run_launcher(
                    [flag],
                    environ={},
                    host=ForbiddenHost(),
                    stdout=stdout,
                    stderr=stderr,
                )

                self.assertEqual(code, 0)
                self.assertEqual(stderr.getvalue(), "")
                output = stdout.getvalue()
                self.assertIn("usage:", output)
                self.assertIn("[-h]", output)
                self.assertIn("[--prepare-only]", output)
                self.assertIn("[disc]", output)
                self.assertIn("path to the user's Tekken 3 USA disc image", output)


if __name__ == "__main__":
    unittest.main()
