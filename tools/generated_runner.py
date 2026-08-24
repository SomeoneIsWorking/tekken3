"""Drive the already-built generated-boundary executable and capture its evidence."""

from __future__ import annotations

import pathlib

from boot_oracle import run_process
from provision_executable import Refused


def capture_generated_text(
    runner: pathlib.Path,
    executable: pathlib.Path,
    entry: int,
    direct_main: int,
    target: int,
    main_lo: int,
    main_hi: int,
    timeout: float,
) -> str:
    result = run_process(
        [
            str(runner),
            str(executable),
            f"0x{entry:08X}",
            f"0x{direct_main:08X}",
            f"0x{target:08X}",
            f"0x{main_lo:08X}",
            f"0x{main_hi:08X}",
        ],
        timeout,
    )
    if result.returncode != 0:
        raise Refused(
            f"generated runner exited {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout
