#!/usr/bin/env python3
"""Static, artifact, and path checks for the V35 boot four-dot trial."""

from __future__ import annotations

import math
from pathlib import Path

import check_firmware_extended_y_v34 as v34


ROOT = Path(__file__).resolve().parents[1]
WRITER_TEST_H = ROOT / "TASK" / "writer_test.h"
WRITER_TEST_C = ROOT / "TASK" / "writer_test.c"
GCODE_H = ROOT / "TASK" / "gcode_serial.h"
MAIN_C = ROOT / "main.c"
FIRMWARE_HEX = ROOT / "keil" / "PAPER_A4_BOOT_PATROL_4DOT_TRIAL_V35.hex"

POINTS = (
    (35.0, 55.0),
    (175.0, 55.0),
    (175.0, 255.0),
    (35.0, 255.0),
)
SAFE_USER = (98.78123618573946, 55.3677149363441)
LEG_MAX_MM = 140.0


def require(source: str, tokens: tuple[str, ...], name: str) -> None:
    missing = [token for token in tokens if token not in source]
    if missing:
        raise AssertionError(f"{name} missing: {missing}")


def split_legs(
    start: tuple[float, float], target: tuple[float, float]
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    legs = []
    current = start
    while True:
        delta_x = target[0] - current[0]
        delta_y = target[1] - current[1]
        span = max(abs(delta_x), abs(delta_y))
        ratio = min(1.0, LEG_MAX_MM / span) if span > 0.0 else 1.0
        endpoint = (
            current[0] + delta_x * ratio,
            current[1] + delta_y * ratio,
        )
        legs.append((current, endpoint))
        current = endpoint
        if ratio >= 1.0:
            return tuple(legs)


def main() -> None:
    writer_test_h = WRITER_TEST_H.read_text(encoding="utf-8")
    writer_test_c = WRITER_TEST_C.read_text(encoding="utf-8")
    gcode_h = GCODE_H.read_text(encoding="utf-8")
    main_c = MAIN_C.read_text(encoding="utf-8")

    require(writer_test_h, (
        "WRITER_TEST_BOOT_PATROL_4DOT_ENABLE (1u)",
        '"PAPER_A4_BOOT_PATROL_4DOT_TRIAL_V35"',
        "WriterTest_Startup_Is_Complete",
        "WriterTest_Startup_Succeeded",
    ), "writer test header")
    require(writer_test_c, (
        "WRITER_BOOT_START_DELAY_MS           (3000u)",
        "WRITER_BOOT_MOVE_LEG_MAX_MM          (140.0f)",
        '{"LOWER_LEFT",  35.0f,  55.0f}',
        '{"LOWER_RIGHT", 175.0f, 55.0f}',
        '{"UPPER_RIGHT", 175.0f, 255.0f}',
        '{"UPPER_LEFT",  35.0f, 255.0f}',
        "sequence=PATROL_UP_THEN_4DOT",
        "phase=SAFE_WAYPOINT",
        "action=MOVE_LEG",
        "action=PEN_DOWN",
        "action=PEN_UP",
        "runtime_limit_active",
        "allowed=STATUS_STOP",
        "cloud_locked=0 gcode_ready=1",
    ), "boot test source")
    require(gcode_h, (
        '"PAPER_A4_BOOT_PATROL_4DOT_TRIAL_V35"',
    ), "G-code build")
    require(main_c, (
        "if (!cloud_initialized)",
        "WriterTest_Startup_Is_Complete()",
        "WriterCloud_Init(startup_ok)",
        "cloud online with needs_rehome=1",
    ), "startup cloud interlock")

    user_points = tuple(v34.paper_to_user(*point) for point in POINTS)
    endpoint_worst = min(v34.joint_margin(*point) for point in user_points)
    if endpoint_worst < 15.0:
        raise AssertionError(f"four-dot endpoint margin {endpoint_worst:.3f} deg")

    route = (*user_points, *user_points)
    current = SAFE_USER
    path_worst = float("inf")
    maximum_segments = 0
    leg_count = 0
    for target in route:
        for start, end in split_legs(current, target):
            span = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
            segment_count = max(1, math.ceil(span))
            maximum_segments = max(maximum_segments, segment_count)
            leg_count += 1
            for index in range(1, segment_count + 1):
                ratio = index / segment_count
                sample = (
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                )
                path_worst = min(path_worst, v34.joint_margin(*sample))
            current = end

    if maximum_segments > 141:
        raise AssertionError(f"planner segment overflow: {maximum_segments}")
    if path_worst < 8.0:
        raise AssertionError(f"patrol path joint margin {path_worst:.3f} deg")

    firmware = v34.intel_hex_payload(FIRMWARE_HEX)
    for token in (
        b"PAPER_A4_BOOT_PATROL_4DOT_TRIAL_V35",
        b"sequence=PATROL_UP_THEN_4DOT",
        b"phase=SAFE_WAYPOINT",
        b"action=MOVE_LEG",
        b"action=PEN_DOWN",
        b"cloud_locked=0 gcode_ready=1",
    ):
        if token not in firmware:
            raise AssertionError(f"firmware HEX missing: {token!r}")

    print(
        "PASS: V35 boot patrol then four-dot test; "
        f"points={len(POINTS)} legs={leg_count} "
        f"max_segments={maximum_segments} "
        f"endpoint_margin={endpoint_worst:.3f}deg "
        f"path_margin_after_safe_waypoint={path_worst:.3f}deg"
    )


if __name__ == "__main__":
    main()
