#!/usr/bin/env python3
"""Static, artifact, and integer-DDA checks for the V33 AMASS firmware."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from check_firmware_junction_planner_v32 import parse_ihex


STEPPER_H = ROOT / "APP" / "stepper" / "Inc" / "app_stepper.h"
STEPPER_C = ROOT / "APP" / "stepper" / "Src" / "app_stepper.c"
MOTION_H = ROOT / "APP" / "Inc" / "app_writer_motion.h"
PAPER_MAP_H = ROOT / "APP" / "Inc" / "app_writer_paper_map.h"
GCODE_H = ROOT / "TASK" / "gcode_serial.h"
GCODE_C = ROOT / "TASK" / "gcode_serial.c"
BUILD_LOG = ROOT / "keil" / "build_amass_v33_log.txt"
HEX_PATH = (
    ROOT / "keil" / "PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33.hex"
)
BUILD_ID = b"PAPER_A4_STANDARD_GCODE_AMASS_PLANNER_V33"
MAX_LEVEL = 3
EXPECTED_SHA256 = (
    "B88F0E3C856A0C28E00F3E751FBE2A835E8A4A396BB7B2AAEC9B25775C2A402D"
)


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label} missing: {needle}")


def simulate_amass(
    stage1_steps: int,
    stage2_steps: int,
    level: int,
) -> tuple[list[int], list[int], int]:
    master_steps = max(stage1_steps, stage2_steps)
    if master_steps <= 0 or not 0 <= level <= MAX_LEVEL:
        raise AssertionError("invalid simulated DDA")
    denominator = master_steps << MAX_LEVEL
    event_count = master_steps << level
    increment1 = stage1_steps << (MAX_LEVEL - level)
    increment2 = stage2_steps << (MAX_LEVEL - level)
    error1 = denominator // 2
    error2 = denominator // 2
    pulses1: list[int] = []
    pulses2: list[int] = []
    for event in range(1, event_count + 1):
        error1 += increment1
        if error1 >= denominator:
            error1 -= denominator
            pulses1.append(event)
        error2 += increment2
        if error2 >= denominator:
            error2 -= denominator
            pulses2.append(event)
    return pulses1, pulses2, event_count


def audit_integer_dda() -> dict[str, int]:
    cases = 0
    for master_steps in range(1, 65):
        for minor_steps in range(master_steps + 1):
            for swapped in (False, True):
                stage1 = minor_steps if swapped else master_steps
                stage2 = master_steps if swapped else minor_steps
                for level in range(MAX_LEVEL + 1):
                    pulses1, pulses2, event_count = simulate_amass(
                        stage1, stage2, level
                    )
                    if len(pulses1) != stage1 or len(pulses2) != stage2:
                        raise AssertionError(
                            "AMASS changed an endpoint pulse total: "
                            f"{stage1},{stage2},L{level}"
                        )
                    if (
                        any(a >= b for a, b in zip(pulses1, pulses1[1:]))
                        or any(a >= b for a, b in zip(pulses2, pulses2[1:]))
                    ):
                        raise AssertionError("non-monotonic AMASS pulse events")
                    if event_count != master_steps << level:
                        raise AssertionError("unexpected AMASS event count")
                    cases += 1
    return {"cases": cases}


def main() -> None:
    stepper_h = STEPPER_H.read_text(encoding="utf-8")
    stepper_c = STEPPER_C.read_text(encoding="utf-8")
    motion_h = MOTION_H.read_text(encoding="utf-8")
    paper_map_h = PAPER_MAP_H.read_text(encoding="utf-8")
    gcode_h = GCODE_H.read_text(encoding="utf-8")
    gcode_c = GCODE_C.read_text(encoding="utf-8")
    build_log = BUILD_LOG.read_text(encoding="utf-8", errors="replace")

    for text, needle, label in (
        (
            stepper_h,
            "#define APP_STEPPER_AMASS_ENABLE (1u)",
            "AMASS enable",
        ),
        (
            stepper_h,
            "#define APP_STEPPER_AMASS_MAX_LEVEL (3u)",
            "AMASS maximum level",
        ),
        (
            stepper_c,
            "App_Stepper_Dual_Amass_Level",
            "AMASS level selector",
        ),
        (
            stepper_c,
            "master_steps << APP_STEPPER_AMASS_MAX_LEVEL",
            "fixed high-resolution DDA denominator",
        ),
        (
            stepper_c,
            "master_steps << s_dda.amass_level",
            "AMASS event count",
        ),
        (
            stepper_c,
            "App_Stepper_Dual_Irq_Freq",
            "AMASS timer overdrive",
        ),
        (
            gcode_h,
            BUILD_ID.decode("ascii"),
            "V33 build ID",
        ),
        (
            gcode_c,
            "amass=%u amass_max=%u",
            "startup AMASS report",
        ),
        (
            motion_h,
            "#define APP_WRITER_DIRECTION_COMP_ENABLE     (0u)",
            "direction compensation remains disabled",
        ),
        (
            paper_map_h,
            '"A4_BASE_QUADRATIC_XSCALE_NO_SBOW_CAL_V8"',
            "paper map remains V8",
        ),
        (
            paper_map_h,
            "#define APP_WRITER_PAPER_S_BOW_CORRECTION_ENABLE (0u)",
            "S-bow remains disabled",
        ),
        (
            build_log,
            "0 Error(s), 0 Warning(s).",
            "clean Keil build",
        ),
    ):
        require(text, needle, label)
    if "Target not created" in build_log:
        raise AssertionError("Keil target was not created")

    dda = audit_integer_dda()
    binary, records, data_bytes = parse_ihex(HEX_PATH)
    if BUILD_ID not in binary:
        raise AssertionError("V33 build ID missing from Intel HEX")
    digest = hashlib.sha256(HEX_PATH.read_bytes()).hexdigest().upper()
    if digest != EXPECTED_SHA256:
        raise AssertionError(f"unexpected V33 HEX SHA-256: {digest}")
    print(
        "firmware_amass_v33=PASS "
        "build_errors=0 build_warnings=0 "
        f"integer_dda_cases={dda['cases']} endpoint_pulses=EXACT "
        "amass_levels=0..3 draw_40_120Hz=LEVEL3 "
        "dircomp=OFF sbow=OFF paper_map=UNCHANGED "
        f"hex_records={records} data_bytes={data_bytes} sha256={digest}"
    )


if __name__ == "__main__":
    main()
