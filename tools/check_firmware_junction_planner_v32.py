#!/usr/bin/env python3
"""Static and artifact checks for the V32 joint-junction planner firmware."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPPER_H = ROOT / "APP" / "stepper" / "Inc" / "app_stepper.h"
STEPPER_C = ROOT / "APP" / "stepper" / "Src" / "app_stepper.c"
MOTION_H = ROOT / "APP" / "Inc" / "app_writer_motion.h"
GCODE_H = ROOT / "TASK" / "gcode_serial.h"
BUILD_LOG = ROOT / "keil" / "build_junction_planner_v32_log.txt"
HEX_PATH = (
    ROOT
    / "keil"
    / "PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32.hex"
)
BUILD_ID = b"PAPER_A4_STANDARD_GCODE_JUNCTION_PLANNER_V32"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label} missing: {needle}")


def parse_ihex(path: Path) -> tuple[bytes, int, int]:
    image: dict[int, int] = {}
    upper = 0
    records = 0

    for raw_line in path.read_text(encoding="ascii").splitlines():
        if not raw_line.startswith(":"):
            raise AssertionError("invalid Intel HEX record")
        record = bytes.fromhex(raw_line[1:])
        if (sum(record) & 0xFF) != 0:
            raise AssertionError("Intel HEX checksum mismatch")
        length = record[0]
        address = (record[1] << 8) | record[2]
        record_type = record[3]
        data = record[4 : 4 + length]
        records += 1
        if record_type == 0:
            base = upper + address
            for offset, value in enumerate(data):
                image[base + offset] = value
        elif record_type == 4:
            upper = int.from_bytes(data, "big") << 16
        elif record_type == 1:
            break

    if not image:
        raise AssertionError("Intel HEX contains no data")
    start = min(image)
    end = max(image) + 1
    binary = bytes(image.get(address, 0xFF) for address in range(start, end))
    return binary, records, len(image)


def junction_frequency(
    previous: tuple[int, int],
    current: tuple[int, int],
    previous_frequency: int = 120,
    current_frequency: int = 120,
) -> int:
    scale = 1024
    floor = 40

    if any(
        a and b and ((a < 0) != (b < 0))
        for a, b in zip(previous, current)
    ):
        return floor

    def normalized(vector: tuple[int, int]) -> tuple[int, int]:
        master = max(abs(vector[0]), abs(vector[1]))
        return tuple(
            (abs(value) * scale // master) * (-1 if value < 0 else 1)
            for value in vector
        )

    p = normalized(previous)
    c = normalized(current)
    dot = p[0] * c[0] + p[1] * c[1]
    if dot <= 0:
        return floor
    cross = abs(p[0] * c[1] - p[1] * c[0])
    ratio = cross * 100
    base = min(previous_frequency, current_frequency)
    if ratio <= dot * 9:
        result = base
    elif ratio <= dot * 36:
        result = base * 3 // 4
    elif ratio <= dot * 84:
        result = base // 2
    else:
        result = base // 4
    return max(floor, result)


def main() -> None:
    stepper_h = STEPPER_H.read_text(encoding="utf-8")
    stepper_c = STEPPER_C.read_text(encoding="utf-8")
    motion_h = MOTION_H.read_text(encoding="utf-8")
    gcode_h = GCODE_H.read_text(encoding="utf-8")
    build_log = BUILD_LOG.read_text(encoding="utf-8", errors="replace")

    require(
        stepper_h,
        "#define APP_STEPPER_JUNCTION_PLANNER_ENABLE (1u)",
        "planner enable",
    )
    require(stepper_h, "max_entry_freq_hz", "block maximum entry rate")
    require(stepper_h, "planned_exit_freq_hz", "block planned exit rate")
    require(
        stepper_c,
        "App_Stepper_Dual_Junction_Freq",
        "joint-space junction limiter",
    )
    require(
        stepper_c,
        "App_Stepper_Dual_Replan_Queue_Locked",
        "reverse/forward queue replanner",
    )
    require(
        stepper_c,
        "APP_STEPPER_QUEUE_BRAKE_GUARD_STEPS",
        "dynamic braking guard",
    )
    if "APP_STEPPER_QUEUE_DECEL_WINDOW_STEPS" in stepper_c:
        raise AssertionError("legacy final-only deceleration window still present")
    require(
        motion_h,
        "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
        "direction compensation remains disabled",
    )
    require(gcode_h, BUILD_ID.decode("ascii"), "unique firmware ID")
    require(build_log, "0 Error(s), 0 Warning(s).", "clean Keil build")
    if "Target not created" in build_log:
        raise AssertionError("Keil target was not created")

    if junction_frequency((100, 50), (100, 50)) != 120:
        raise AssertionError("straight junction should retain nominal rate")
    if junction_frequency((100, 50), (-100, 50)) != 40:
        raise AssertionError("joint reversal should force exact-stop rate")
    if junction_frequency((100, 0), (0, 100)) != 40:
        raise AssertionError("right-angle junction should force low rate")

    binary, records, data_bytes = parse_ihex(HEX_PATH)
    if BUILD_ID not in binary:
        raise AssertionError("V32 build ID missing from Intel HEX")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    print(
        "junction_planner_v32=PASS "
        "build_errors=0 build_warnings=0 "
        "straight=120Hz reversal=40Hz right_angle=40Hz "
        f"hex_records={records} data_bytes={data_bytes} sha256={digest}"
    )


if __name__ == "__main__":
    main()
