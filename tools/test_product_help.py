#!/usr/bin/env python3
"""Contract test for the built product's dependency-free help path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: test_product_help.py <tekken3_port>", file=sys.stderr)
        return 2

    product = Path(argv[1])
    for arguments in (("-h",), ("--help",), ("ignored-disc", "--help")):
        result = subprocess.run(
            [product, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={"PATH": os.defpath},
        )
        if result.returncode != 0:
            print(
                f"product {arguments} exited {result.returncode}: {result.stderr}",
                file=sys.stderr,
            )
            return 1
        if "usage: tekken3_port [disc]" not in result.stdout:
            print(f"product {arguments} omitted usage: {result.stdout!r}", file=sys.stderr)
            return 1
        if result.stderr or "watchdog" in result.stdout.lower():
            print(
                f"product {arguments} reached runtime discovery: "
                f"stdout={result.stdout!r} stderr={result.stderr!r}",
                file=sys.stderr,
            )
            return 1

    print("product_help: PASS — -h/--help print usage and exit 0 before runtime or disc discovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
