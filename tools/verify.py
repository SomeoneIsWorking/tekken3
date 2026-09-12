#!/usr/bin/env python3
"""Run Tekken 3's complete asset-free Linux product gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PSXPORT = ROOT / "external" / "psxport"


def main() -> int:
    bootstrap = subprocess.run(
        [sys.executable, ROOT / "tools" / "psxport_sync.py", "--auto"],
        cwd=ROOT,
        check=False,
    )
    if bootstrap.returncode:
        print(f"[verify] FAILED: PSXPort bootstrap exited {bootstrap.returncode}", file=sys.stderr)
        return bootstrap.returncode

    sys.path.insert(0, str(PSXPORT / "tools"))
    from port.consumer_verify import ConsumerVerifyConfig, run_consumer_verification

    build = ROOT / "build" / "ci"
    return run_consumer_verification(
        ConsumerVerifyConfig(
            name="Tekken 3",
            root=ROOT,
            build=build,
            psxport=PSXPORT,
            product=build / "bin" / "tekken3_port",
            cmake_module=ROOT / "cmake" / "tekken3_port.cmake",
            test_regex=(
                r"^tekken3_(product_help_contract|runtime_seam|runtime_contract|"
                r"frame_loop_contract|bounded_guest_call|decompressor_probe_contract|decompressor_lightrec_selftest|"
                r"cd_protocol_contract|gpu_sync_contract|"
                r"widescreen_contract|irq_oracle_selftest|launcher_selftest|"
                r"launcher_help_contract)$"
            ),
            cmake_definitions=("-DPSXPORT_BUILD_SMOKE=OFF",),
            build_targets=("cpp_policy",),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
