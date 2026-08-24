"""Validate a generated PSX BIOS-vector edge from captured CPU state.

The generated runner reports the vector and function registers after the measured wrapper
returns. This module owns the marker grammar and exact-state contract so the boundary
orchestrator does not grow another independent parser or expected-value check.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from provision_executable import Mismatch, Refused

BIOS_EDGE_RE = re.compile(
    r"^# RECOMP-BIOS vector=0x(?P<vector>[0-9A-Fa-f]{8}) "
    r"function=0x(?P<function>[0-9A-Fa-f]{2})$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class BiosEdgeObservation:
    vector: int
    function: int


def marker(vector: int, function: int) -> str:
    return f"# RECOMP-BIOS vector=0x{vector:08X} function=0x{function:02X}\n"


def parse_bios_edge(
    text: str, *, expected_vector: int, expected_function: int
) -> BiosEdgeObservation:
    markers = BIOS_EDGE_RE.findall(text)
    if not markers:
        raise Refused(
            "generated runner emitted no BIOS-edge note; the measured wrapper "
            "was never dispatched"
        )
    if len(markers) > 1:
        raise Refused(
            f"generated runner emitted {len(markers)} BIOS-edge notes; expected exactly one"
        )

    observation = BiosEdgeObservation(
        vector=int(markers[0][0], 16),
        function=int(markers[0][1], 16),
    )
    if (
        observation.vector != expected_vector
        or observation.function != expected_function
    ):
        raise Mismatch(
            "generated BIOS edge differs from the measured executable: "
            f"vector=0x{observation.vector:08X} function=0x{observation.function:02X}, "
            f"expected 0x{expected_vector:08X}/0x{expected_function:02X}"
        )
    return observation


def validate_bios_edge(
    text: str,
    fields: Mapping[str, int],
    *,
    expected_return: int,
    expected_vector: int,
    expected_function: int,
) -> BiosEdgeObservation:
    observation = parse_bios_edge(
        text,
        expected_vector=expected_vector,
        expected_function=expected_function,
    )
    expected = {
        "pc": expected_return,
        "ra": expected_return,
        "t1": expected_function,
        "t2": expected_vector,
    }
    mismatches = tuple(
        f"{name}=0x{fields[name]:08X} (expected 0x{value:08X})"
        for name, value in expected.items()
        if fields[name] != value
    )
    if mismatches:
        raise Mismatch(
            "generated state at the BIOS-call return differs from the measured caller/wrapper edge: "
            + ", ".join(mismatches)
        )
    return observation


def selftest_bios_edge(
    *, expected_return: int, expected_vector: int, expected_function: int
) -> None:
    good = marker(expected_vector, expected_function)
    good_fields = {
        "pc": expected_return,
        "ra": expected_return,
        "t1": expected_function,
        "t2": expected_vector,
    }
    validate_bios_edge(
        good,
        good_fields,
        expected_return=expected_return,
        expected_vector=expected_vector,
        expected_function=expected_function,
    )
    print(
        "PASS BIOS-edge parser: the measured vector/function fixture parses "
        f"(vector 0x{expected_vector:08X} function 0x{expected_function:02X})"
    )

    negative_fixtures = (
        ("missing", ""),
        ("duplicate", good + good),
        ("wrong-vector", marker(expected_vector ^ 4, expected_function)),
        ("wrong-function", marker(expected_vector, expected_function ^ 1)),
    )
    for label, text in negative_fixtures:
        try:
            parse_bios_edge(
                text,
                expected_vector=expected_vector,
                expected_function=expected_function,
            )
        except (Refused, Mismatch):
            continue
        raise Refused(f"BIOS-edge parser accepted the {label} note fixture")
    print(
        "PASS refusal: missing, duplicate, wrong-vector, and wrong-function "
        "BIOS-edge notes are rejected"
    )

    try:
        validate_bios_edge(
            good,
            {**good_fields, "ra": expected_return ^ 4},
            expected_return=expected_return,
            expected_vector=expected_vector,
            expected_function=expected_function,
        )
    except Mismatch:
        print("PASS refusal: wrong BIOS-return register state is rejected")
    else:
        raise Refused("BIOS-edge validator accepted wrong return-register state")
