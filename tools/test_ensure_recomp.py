#!/usr/bin/env python3
"""Hermetic tests for the whole-program substrate freshness contract."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ensure_recomp

SCRATCH = ensure_recomp.ROOT / "scratch/raw"


class EnsureRecompTest(unittest.TestCase):
    def setUp(self) -> None:
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="ensure-recomp-test-", dir=SCRATCH
        )
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_file_hash_changes_when_an_input_changes(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        first.write_bytes(b"retail")
        second.write_bytes(b"seeds")
        before = ensure_recomp.file_hash([first, second])
        second.write_bytes(b"different seeds")
        self.assertNotEqual(before, ensure_recomp.file_hash([first, second]))

    def test_complete_output_requires_every_manifest_source(self) -> None:
        generated = self.root / "generated"
        generated.mkdir()
        (generated / "rec_sources.cmake").write_text(
            "set(GEN_REC_SRCS\n  shard_0.c\n  shard_disp.c\n)\n"
        )
        for name in (
            "shard_0.c",
            "shard_disp.c",
            "rec_decls.h",
            "overlay_table.h",
        ):
            (generated / name).write_text("// fixture\n")
        (generated / ".recomp_version").write_text("test-version\n")
        expected_header = "// generated fixture\n"
        (generated / "tekken3_program.h").write_text(expected_header)

        with (
            mock.patch.object(ensure_recomp, "GENERATED", generated),
            mock.patch.object(
                ensure_recomp,
                "expected_program_header",
                return_value=expected_header,
            ),
        ):
            self.assertTrue(ensure_recomp.output_complete("test-version"))
            (generated / "shard_disp.c").unlink()
            self.assertFalse(ensure_recomp.output_complete("test-version"))


if __name__ == "__main__":
    unittest.main()
